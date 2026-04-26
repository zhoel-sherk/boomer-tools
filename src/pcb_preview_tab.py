"""PCB Preview tab: QGraphicsView + Gerber layers + PnP overlay."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtSvg import QSvgRenderer

from pcb_preview.alignment import Similarity2D
from pcb_preview.footprint_db import FootprintStore
from pcb_preview.gerber_io import load_gerber_svg, peek_rs274x_linear_unit, scale_bbox_mm
from pcb_preview.types import BBoxMM, FootprintOutlineMM, GerberSvgPayload, PlacementRecord

import pcb_preview_bridge


# Centroid marker radius in mm (scene units); stroke is cosmetic (pixels) so it stays visible.
_CENTROID_RADIUS_MM = 0.45
_SEL_RING_SCALE = 2.8
# Ref label height in scene mm (~font * scale); was 0.12 → ~3× for 0402 at zoom.
_LABEL_SCENE_SCALE = 0.36
# Half-length of each arm of the centroid X-cross (mm, local item space).
_CROSS_HALF_MM = 0.9
# Gerber raster: pixels per mm of SVG viewBox (higher = sharper, more memory).
_GERBER_PX_PER_MM = 14.0


def _outline_to_path(outline: FootprintOutlineMM, y_flip: bool = True) -> QtGui.QPainterPath:
    path = QtGui.QPainterPath()
    fy = -1.0 if y_flip else 1.0

    def qy(y: float) -> float:
        return y * fy

    for ln in outline.lines:
        path.moveTo(ln.x1, qy(ln.y1))
        path.lineTo(ln.x2, qy(ln.y2))
    for c in outline.circles:
        cy = qy(c.cy)
        path.addEllipse(QtCore.QRectF(c.cx - c.radius_mm, cy - c.radius_mm, 2 * c.radius_mm, 2 * c.radius_mm))
    for p in outline.pads:
        w, h = p.width_mm, p.height_mm
        rect = QtCore.QRectF(-w / 2, -h / 2, w, h)
        poly = QtGui.QPolygonF(rect)
        tr = QtGui.QTransform()
        tr.rotate(-p.rotation_deg if y_flip else p.rotation_deg)
        poly = tr.map(poly)
        poly.translate(p.cx, qy(p.cy))
        path.addPolygon(poly)
    return path


def _similarity_to_qtransform(sim: Similarity2D) -> QtGui.QTransform:
    s, c, sn = sim.scale, sim.cos_t, sim.sin_t
    return QtGui.QTransform(s * c, s * sn, -s * sn, s * c, sim.tx, sim.ty)


def _pnp_mirror_transform(mx: int, my: int) -> QtGui.QTransform:
    """Mirror PnP in board mm before similarity: x' = mx*x, y' = my*y (mx,my ∈ {−1, +1})."""
    return QtGui.QTransform(float(mx), 0.0, 0.0, float(my), 0.0, 0.0)


def _compose_pnp_preview_transform(sim: Similarity2D, mirror_x: int, mirror_y: int) -> QtGui.QTransform:
    """Apply mirror in placement space, then similarity: p ↦ sim(mirror(p))."""
    return _similarity_to_qtransform(sim) * _pnp_mirror_transform(mirror_x, mirror_y)


def _bbox_union(a: QtCore.QRectF, b: QtCore.QRectF) -> QtCore.QRectF:
    if not a.isValid():
        return b
    if not b.isValid():
        return a
    return a.united(b)


class ZoomGraphicsView(QtWidgets.QGraphicsView):
    """Wheel zoom (anchor under mouse); scene coordinates stay in mm for PnP + Gerber."""

    def __init__(self, scene: QtWidgets.QGraphicsScene, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if event.angleDelta().y() == 0:
            return super().wheelEvent(event)
        factor = 1.15 ** (event.angleDelta().y() / 120.0)
        self.scale(factor, factor)
        event.accept()


class PlacementGroupItem(QtWidgets.QGraphicsItemGroup):
    """One ref: centroid (always) + optional footprint path + label."""

    def __init__(self, placement: PlacementRecord, outline: FootprintOutlineMM):
        super().__init__()
        self._placement = placement
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setData(0, placement.ref)

        r = _CENTROID_RADIUS_MM
        self._dot = QtWidgets.QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        self._dot.setBrush(QtGui.QBrush(QtGui.QColor(255, 120, 20, 220)))
        dp = QtGui.QPen(QtGui.QColor(180, 60, 0))
        dp.setCosmetic(True)
        dp.setWidthF(2.0)
        self._dot.setPen(dp)
        self._dot.setZValue(1)
        self.addToGroup(self._dot)

        path = _outline_to_path(outline)
        self._path_item = QtWidgets.QGraphicsPathItem(path)
        pp = QtGui.QPen(QtGui.QColor(60, 140, 255))
        pp.setCosmetic(True)
        pp.setWidthF(2.0)
        pp.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        pp.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        self._path_item.setPen(pp)
        self._path_item.setZValue(0)
        self.addToGroup(self._path_item)

        h = _CROSS_HALF_MM
        self._cross1 = QtWidgets.QGraphicsLineItem(-h, -h, h, h)
        self._cross2 = QtWidgets.QGraphicsLineItem(-h, h, h, -h)
        xp = QtGui.QPen(QtGui.QColor(255, 210, 120))
        xp.setCosmetic(True)
        xp.setWidthF(1.5)
        xp.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        self._cross1.setPen(xp)
        self._cross2.setPen(xp)
        self._cross1.setZValue(0.5)
        self._cross2.setZValue(0.5)
        self.addToGroup(self._cross1)
        self.addToGroup(self._cross2)

        self._label = QtWidgets.QGraphicsSimpleTextItem(placement.ref)
        self._label.setBrush(QtGui.QBrush(QtGui.QColor(255, 235, 160)))
        lf = self._label.font()
        lf.setFamily("Sans")
        lf.setPointSizeF(10.0)
        self._label.setFont(lf)
        self._label.setPos(r + 0.2, -r - 0.2)
        self._label.setScale(_LABEL_SCENE_SCALE)
        self._label.setZValue(2)
        self.addToGroup(self._label)

        rr = _CENTROID_RADIUS_MM * _SEL_RING_SCALE
        self._sel_ring = QtWidgets.QGraphicsEllipseItem(-rr, -rr, 2 * rr, 2 * rr)
        rp = QtGui.QPen(QtGui.QColor(255, 255, 80))
        rp.setCosmetic(True)
        rp.setWidthF(4.0)
        rp.setStyle(QtCore.Qt.PenStyle.DashLine)
        self._sel_ring.setPen(rp)
        self._sel_ring.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        self._sel_ring.setZValue(3)
        self._sel_ring.setVisible(False)
        self.addToGroup(self._sel_ring)

        self.setPos(placement.x_mm, placement.y_mm)
        self.setRotation(-placement.rotation_deg)

    def path_item(self) -> QtWidgets.QGraphicsPathItem:
        return self._path_item

    def ref(self) -> str:
        return self._placement.ref

    def apply_selection_style(self, selected: bool, ref_a: bool = False, ref_b: bool = False) -> None:
        ring_on = selected or ref_a or ref_b
        self._sel_ring.setVisible(ring_on)
        if selected:
            dp = QtGui.QPen(QtGui.QColor(255, 255, 80))
            dp.setCosmetic(True)
            dp.setWidthF(4.0)
            dp.setStyle(QtCore.Qt.PenStyle.DashLine)
            self._sel_ring.setPen(dp)
        elif ref_a and not ref_b:
            ap = QtGui.QPen(QtGui.QColor(80, 220, 255))
            ap.setCosmetic(True)
            ap.setWidthF(5.0)
            ap.setStyle(QtCore.Qt.PenStyle.SolidLine)
            self._sel_ring.setPen(ap)
        elif ref_b and not ref_a:
            bp = QtGui.QPen(QtGui.QColor(255, 120, 255))
            bp.setCosmetic(True)
            bp.setWidthF(5.0)
            bp.setStyle(QtCore.Qt.PenStyle.SolidLine)
            self._sel_ring.setPen(bp)
        elif ref_a and ref_b:
            dp = QtGui.QPen(QtGui.QColor(255, 255, 255))
            dp.setCosmetic(True)
            dp.setWidthF(5.0)
            dp.setStyle(QtCore.Qt.PenStyle.DashLine)
            self._sel_ring.setPen(dp)
        elif ring_on:
            mp = QtGui.QPen(QtGui.QColor(160, 200, 255))
            mp.setCosmetic(True)
            mp.setWidthF(3.0)
            mp.setStyle(QtCore.Qt.PenStyle.DotLine)
            self._sel_ring.setPen(mp)

        if selected:
            p = QtGui.QPen(QtGui.QColor(255, 90, 60))
            p.setCosmetic(True)
            p.setWidthF(4.5)
            self._path_item.setPen(p)
            cxp = QtGui.QPen(QtGui.QColor(255, 255, 200))
            cxp.setCosmetic(True)
            cxp.setWidthF(2.0)
            cxp.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            self._cross1.setPen(cxp)
            self._cross2.setPen(cxp)
            self._dot.setBrush(QtGui.QBrush(QtGui.QColor(255, 220, 60, 255)))
            dr = _CENTROID_RADIUS_MM * 1.35
            self._dot.setRect(-dr, -dr, 2 * dr, 2 * dr)
            self._label.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 220)))
        elif ref_a or ref_b:
            p = QtGui.QPen(QtGui.QColor(120, 200, 255))
            p.setCosmetic(True)
            p.setWidthF(2.8)
            self._path_item.setPen(p)
            cxp = QtGui.QPen(QtGui.QColor(255, 230, 160))
            cxp.setCosmetic(True)
            cxp.setWidthF(1.8)
            cxp.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            self._cross1.setPen(cxp)
            self._cross2.setPen(cxp)
            self._dot.setBrush(QtGui.QBrush(QtGui.QColor(255, 180, 40, 230)))
            dr = _CENTROID_RADIUS_MM * 1.12
            self._dot.setRect(-dr, -dr, 2 * dr, 2 * dr)
            self._label.setBrush(QtGui.QBrush(QtGui.QColor(255, 250, 200)))
        else:
            p = QtGui.QPen(QtGui.QColor(60, 140, 255))
            p.setCosmetic(True)
            p.setWidthF(2.0)
            self._path_item.setPen(p)
            cxp = QtGui.QPen(QtGui.QColor(255, 210, 120))
            cxp.setCosmetic(True)
            cxp.setWidthF(1.5)
            cxp.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            self._cross1.setPen(cxp)
            self._cross2.setPen(cxp)
            self._dot.setBrush(QtGui.QBrush(QtGui.QColor(255, 120, 20, 220)))
            dr = _CENTROID_RADIUS_MM
            self._dot.setRect(-dr, -dr, 2 * dr, 2 * dr)
            self._label.setBrush(QtGui.QBrush(QtGui.QColor(255, 235, 160)))


class PnpArrowNudgeBar(QtWidgets.QWidget):
    """Компактный ромб: стрелки вокруг поля шага (мм); не растягивается по ширине окна."""

    nudgeRequested = QtCore.Signal(float, float)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._step = QtWidgets.QLineEdit("0.5")
        self._step.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._step.setFixedWidth(46)
        self._step.setMaximumHeight(30)
        self._step.setToolTip("Шаг в миллиметрах для кнопок направления")
        val = QtGui.QDoubleValidator(0.0001, 1.0e9, 6, self)
        val.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
        self._step.setValidator(val)
        st = self.style()
        lay = QtWidgets.QGridLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        gap = 4
        lay.setHorizontalSpacing(gap)
        lay.setVerticalSpacing(gap)
        lay.setColumnStretch(0, 0)
        lay.setColumnStretch(1, 0)
        lay.setColumnStretch(2, 0)
        lay.setRowStretch(0, 0)
        lay.setRowStretch(1, 0)
        lay.setRowStretch(2, 0)
        sz = 36
        icon_sz = 28
        for gr, gc, dx, dy, spix in (
            (0, 1, 0.0, -1.0, QtWidgets.QStyle.StandardPixmap.SP_ArrowUp),
            (1, 0, -1.0, 0.0, QtWidgets.QStyle.StandardPixmap.SP_ArrowLeft),
            (1, 2, 1.0, 0.0, QtWidgets.QStyle.StandardPixmap.SP_ArrowRight),
            (2, 1, 0.0, 1.0, QtWidgets.QStyle.StandardPixmap.SP_ArrowDown),
        ):
            tb = QtWidgets.QToolButton()
            tb.setIcon(st.standardIcon(spix))
            tb.setIconSize(QtCore.QSize(icon_sz, icon_sz))
            tb.setFixedSize(sz, sz)
            tb.setAutoRaise(True)
            tb.setToolTip("Сдвиг PnP")
            tb.setAutoRepeat(True)
            tb.setAutoRepeatDelay(400)
            tb.setAutoRepeatInterval(55)
            tb.clicked.connect(lambda _=False, ux=dx, uy=dy: self._emit_nudge(ux, uy))
            lay.addWidget(tb, gr, gc)
        lay.addWidget(self._step, 1, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        m = lay.contentsMargins()
        w = m.left() + m.right() + 3 * sz + 2 * gap
        h = m.top() + m.bottom() + 3 * sz + 2 * gap
        self.setFixedSize(w, h)

    def step_mm(self) -> float:
        t = self._step.text().strip().replace(",", ".")
        try:
            v = float(t)
            return v if v > 0 else 0.5
        except ValueError:
            return 0.5

    def _emit_nudge(self, dx: float, dy: float) -> None:
        s = self.step_mm()
        self.nudgeRequested.emit(dx * s, dy * s)


@dataclass
class _GerberLayerRow:
    """One loaded Gerber bitmap in the scene."""

    path: str
    display_name: str
    pixmap_item: QtWidgets.QGraphicsPixmapItem
    bbox_mm: BBoxMM


class PcbPreviewTab(QtWidgets.QWidget):
    """Gerber SVG layers + PnP overlay, 2-point alignment, list navigation."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._store = FootprintStore()
        self._placements: list[PlacementRecord] = []
        self._items: dict[str, PlacementGroupItem] = {}
        self._layers: list[_GerberLayerRow] = []
        self._placements_root = QtWidgets.QGraphicsItemGroup()
        self._preview_sim = Similarity2D.identity()
        self._pnp_mirror_x = 1
        self._pnp_mirror_y = 1
        self._px_per_mm = _GERBER_PX_PER_MM

        root = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self._btn_gerber = QtWidgets.QPushButton("Add Gerber layer…")
        self._btn_gerber.setToolTip("Append a Gerber file as a raster layer (paste, silk, etc.)")
        self._btn_gerber.clicked.connect(self._browse_gerber)
        top.addWidget(self._btn_gerber)
        self._btn_clear_layers = QtWidgets.QPushButton("Clear layers")
        self._btn_clear_layers.clicked.connect(self._clear_gerber_layers)
        top.addWidget(self._btn_clear_layers)
        self._btn_import_fp = QtWidgets.QPushButton("Import .kicad_mod…")
        self._btn_import_fp.setToolTip("Register footprint file under the PnP Footprint column key")
        self._btn_import_fp.clicked.connect(self._import_kicad_mod)
        top.addWidget(self._btn_import_fp)
        # --- Временно отключено: ориентиры Gerber / выбор Ref A–B на плате / 2-point similarity ---
        # self._btn_align = QtWidgets.QPushButton("Pick Gerber landmarks…")
        # self._btn_align.setCheckable(True)
        # self._btn_align.toggled.connect(self._on_align_toggled)
        # top.addWidget(self._btn_align)
        # top.addWidget(QtWidgets.QLabel("Ref A:"))
        # self._cb_a = QtWidgets.QComboBox()
        # top.addWidget(self._cb_a)
        # top.addWidget(QtWidgets.QLabel("Ref B:"))
        # self._cb_b = QtWidgets.QComboBox()
        # top.addWidget(self._cb_b)
        # self._cb_a.currentIndexChanged.connect(self._sync_all_placement_styles)
        # self._cb_b.currentIndexChanged.connect(self._sync_all_placement_styles)
        # self._btn_pick_refs = QtWidgets.QPushButton("Pick Ref A/B on board…")
        # self._btn_pick_refs.setCheckable(True)
        # self._btn_pick_refs.setToolTip("Left-click two components: first sets Ref A, second sets Ref B (like Gerber picks)")
        # self._btn_pick_refs.toggled.connect(self._on_pick_refs_toggled)
        # top.addWidget(self._btn_pick_refs)
        # self._btn_apply_sim = QtWidgets.QPushButton("Apply 2-point similarity")
        # self._btn_apply_sim.clicked.connect(self._apply_similarity)
        # top.addWidget(self._btn_apply_sim)
        self._btn_reset = QtWidgets.QPushButton("Reset preview transform")
        self._btn_reset.clicked.connect(self._reset_transform)
        top.addWidget(self._btn_reset)
        self._chk_mirror_x = QtWidgets.QCheckBox("Mirror PnP X")
        self._chk_mirror_x.setToolTip("Отразить X в координатах платы (мм)")
        self._chk_mirror_x.toggled.connect(self._on_mirror_x_toggled)
        top.addWidget(self._chk_mirror_x)
        self._chk_mirror_y = QtWidgets.QCheckBox("Mirror PnP Y")
        self._chk_mirror_y.setToolTip("Отразить Y в координатах платы (мм)")
        self._chk_mirror_y.toggled.connect(self._on_mirror_y_toggled)
        top.addWidget(self._chk_mirror_y)
        self._btn_center = QtWidgets.QPushButton("Center on selection")
        self._btn_center.clicked.connect(self._center_selection)
        self._btn_fit = QtWidgets.QPushButton("Fit all")
        self._btn_fit.setToolTip("Reset view zoom, then zoom to Gerber layers + PnP")
        self._btn_fit.clicked.connect(self._fit_all_with_reset_view)
        top.addWidget(self._btn_fit)
        self._btn_zoom_in = QtWidgets.QPushButton("Zoom +")
        self._btn_zoom_in.setToolTip("Scale view (wheel also works)")
        top.addWidget(self._btn_zoom_in)
        self._btn_zoom_out = QtWidgets.QPushButton("Zoom −")
        self._btn_zoom_out.setToolTip("Scale view (wheel also works)")
        top.addWidget(self._btn_zoom_out)
        top.addStretch()
        root.addLayout(top)

        mid = QtWidgets.QHBoxLayout()
        left_col = QtWidgets.QVBoxLayout()
        grp_u = QtWidgets.QGroupBox("Gerber units (linear)")
        lu = QtWidgets.QVBoxLayout(grp_u)
        self._rb_g_auto = QtWidgets.QRadioButton("Auto (scan %MOIN% / %MOMM%)")
        self._rb_g_mm = QtWidgets.QRadioButton("mm (×1)")
        self._rb_g_in = QtWidgets.QRadioButton("inch → mm (×25.4)")
        self._rb_g_auto.setChecked(True)
        self._rb_g_auto.setToolTip(
            "Reads RS-274X header only. gerbonara usually outputs SVG in mm; scale stays ×1."
        )
        self._rb_g_mm.setToolTip("Assume gerbonara/SVG geometry is already in millimetres.")
        self._rb_g_in.setToolTip(
            "Use only if the layer looks ~25× too small: forces an extra ×25.4 on top of gerbonara output."
        )
        self._bg_gunit = QtWidgets.QButtonGroup(self)
        for rb in (self._rb_g_auto, self._rb_g_mm, self._rb_g_in):
            self._bg_gunit.addButton(rb)
            lu.addWidget(rb)
        left_col.addWidget(grp_u)

        grp_nudge = QtWidgets.QGroupBox("PnP nudge (mm)")
        lnudge = QtWidgets.QVBoxLayout(grp_nudge)
        self._nudge_bar = PnpArrowNudgeBar()
        self._nudge_bar.nudgeRequested.connect(self._on_pnp_nudge_mm)
        lnudge.addWidget(self._nudge_bar, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        left_col.addWidget(grp_nudge)

        grp = QtWidgets.QGroupBox("Gerber layers")
        gl = QtWidgets.QVBoxLayout(grp)
        self._layer_list = QtWidgets.QListWidget()
        self._layer_list.setMinimumWidth(200)
        self._layer_list.setMaximumWidth(280)
        self._layer_list.setToolTip("Toggle visibility. Lower items draw behind upper items.")
        self._layer_list.itemChanged.connect(self._on_layer_item_changed)
        gl.addWidget(self._layer_list)
        btn_rm = QtWidgets.QPushButton("Remove selected layer")
        btn_rm.clicked.connect(self._remove_selected_layer)
        gl.addWidget(btn_rm)
        left_col.addWidget(grp)

        self._list = QtWidgets.QListWidget()
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.itemSelectionChanged.connect(self._on_list_selection)
        left_col.addWidget(QtWidgets.QLabel("PnP refs"))
        left_col.addWidget(self._list, 1)
        mid.addLayout(left_col, 0)

        self._scene = QtWidgets.QGraphicsScene()
        self._scene.setSceneRect(-5, -5, 200, 200)
        self._view = ZoomGraphicsView(self._scene)
        self._view.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self._view.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        mid.addWidget(self._view, 1)
        root.addLayout(mid, 1)

        self._btn_zoom_in.clicked.connect(self._zoom_view_in)
        self._btn_zoom_out.clicked.connect(self._zoom_view_out)

        self._log = QtWidgets.QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setFixedHeight(90)
        root.addWidget(self._log)

        self._scene.addItem(self._placements_root)
        self._placements_root.setZValue(10.0)
        self._set_placements_root_transform()

    def _set_placements_root_transform(self) -> None:
        self._placements_root.setTransform(
            _compose_pnp_preview_transform(self._preview_sim, self._pnp_mirror_x, self._pnp_mirror_y)
        )

    def _append_log(self, msg: str) -> None:
        self._log.appendPlainText(msg)

    def _zoom_view_in(self) -> None:
        self._view.scale(1.2, 1.2)

    def _zoom_view_out(self) -> None:
        self._view.scale(1.0 / 1.2, 1.0 / 1.2)

    def _on_mirror_x_toggled(self, checked: bool) -> None:
        self._pnp_mirror_x = -1 if checked else 1
        self._set_placements_root_transform()
        self._update_scene_rect_from_content()
        self._append_log(f"PnP mirror X: {'on' if checked else 'off'}")

    def _on_mirror_y_toggled(self, checked: bool) -> None:
        self._pnp_mirror_y = -1 if checked else 1
        self._set_placements_root_transform()
        self._update_scene_rect_from_content()
        self._append_log(f"PnP mirror Y: {'on' if checked else 'off'}")

    def _sync_all_placement_styles(self) -> None:
        sel = {it.text() for it in self._list.selectedItems()}
        for ref, g in self._items.items():
            g.setSelected(ref in sel)
            g.apply_selection_style(ref in sel, ref_a=False, ref_b=False)

    def _on_pnp_nudge_mm(self, dx_mm: float, dy_mm: float) -> None:
        refs = [it.text() for it in self._list.selectedItems()]
        if not refs:
            refs = list(self._items.keys())
        delta = QtCore.QPointF(dx_mm, dy_mm)
        for r in refs:
            if r in self._items:
                it = self._items[r]
                it.setPos(it.pos() + delta)
        self._update_scene_rect_from_content()

    def _gerber_user_mm_scale(self, path: str) -> tuple[float, str]:
        if self._rb_g_in.isChecked():
            return 25.4, "UI inch→mm ×25.4"
        if self._rb_g_mm.isChecked():
            return 1.0, "UI mm ×1"
        u = peek_rs274x_linear_unit(path)
        return 1.0, f"Auto header={u!r}; gerbonara→scene ×1"

    def _browse_gerber(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Add Gerber layer",
            "",
            "Gerber (*.gbr *.gtp *.gtl *.gto *.gts *.pho *.ger *.art);;All (*.*)",
        )
        if not path:
            return
        payload = load_gerber_svg(path)
        if payload.errors:
            self._append_log("Gerber: " + "; ".join(payload.errors))
        if not payload.svg:
            return
        u_scale, unit_note = self._gerber_user_mm_scale(path)
        self._append_gerber_layer(payload, u_scale, unit_note)

    def _append_gerber_layer(
        self, payload: GerberSvgPayload, user_mm_scale: float = 1.0, unit_note: str = ""
    ) -> None:
        renderer = QSvgRenderer(QtCore.QByteArray(payload.svg.encode("utf-8")))
        if not renderer.isValid():
            self._append_log("Invalid SVG from gerbonara")
            return
        vb = renderer.viewBoxF()
        w_px = max(2, int(vb.width() * self._px_per_mm + 2))
        h_px = max(2, int(vb.height() * self._px_per_mm + 2))
        img = QtGui.QImage(w_px, h_px, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(img)
        renderer.render(p, QtCore.QRectF(0, 0, w_px, h_px))
        p.end()
        pm = QtGui.QPixmap.fromImage(img)
        item = self._scene.addPixmap(pm)
        item.setTransformationMode(QtCore.Qt.TransformationMode.SmoothTransformation)
        # Raster is w_px×h_px; SVG viewBox is in gerbonara mm. Scale item so one scene unit matches mm.
        s_rx = (vb.width() / float(w_px)) if w_px else 1.0
        s_ry = (vb.height() / float(h_px)) if h_px else 1.0
        s_raster = 0.5 * (s_rx + s_ry)
        item.setScale(s_raster * user_mm_scale)
        item.setPos(vb.x() * user_mm_scale, vb.y() * user_mm_scale)
        base_z = -50.0
        item.setZValue(base_z + float(len(self._layers)) * 0.5)

        name = os.path.basename(payload.source_path)
        bbox_scene = scale_bbox_mm(payload.bbox_mm, user_mm_scale)
        row = _GerberLayerRow(path=payload.source_path, display_name=name, pixmap_item=item, bbox_mm=bbox_scene)
        self._layers.append(row)

        lw_item = QtWidgets.QListWidgetItem(name)
        lw_item.setFlags(
            lw_item.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        lw_item.setCheckState(QtCore.Qt.CheckState.Checked)
        self._layer_list.blockSignals(True)
        self._layer_list.addItem(lw_item)
        self._layer_list.blockSignals(False)

        self._apply_layer_z_order()
        self._update_scene_rect_from_content()
        self._fit_all_content()
        bb = bbox_scene
        extra = f"  [{unit_note}]" if unit_note else ""
        self._append_log(
            f"Gerber layer added: {name}  size {bb.width:.2f}×{bb.height:.2f} mm  "
            f"origin ({bb.min_x:.2f}, {bb.min_y:.2f}) mm{extra}"
        )

    def _apply_layer_z_order(self) -> None:
        """List top → drawn on top (higher z). Bottom row = back."""
        n = min(self._layer_list.count(), len(self._layers))
        for i in range(n):
            self._layers[i].pixmap_item.setZValue(-50.0 + float(i) * 0.5)

    def _on_layer_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self._layer_list.row(item)
        if row < 0 or row >= len(self._layers):
            return
        vis = item.checkState() == QtCore.Qt.CheckState.Checked
        self._layers[row].pixmap_item.setVisible(vis)

    def _remove_selected_layer(self) -> None:
        row = self._layer_list.currentRow()
        if row < 0 or row >= len(self._layers):
            return
        entry = self._layers.pop(row)
        self._scene.removeItem(entry.pixmap_item)
        self._layer_list.takeItem(row)
        self._apply_layer_z_order()
        self._update_scene_rect_from_content()
        self._fit_all_content()

    def _clear_gerber_layers(self) -> None:
        for entry in self._layers:
            self._scene.removeItem(entry.pixmap_item)
        self._layers.clear()
        self._layer_list.clear()
        self._update_scene_rect_from_content()
        self._fit_all_content()
        self._append_log("All Gerber layers cleared.")

    def _placements_scene_rect(self) -> QtCore.QRectF:
        br = QtCore.QRectF()
        for it in self._items.values():
            br = _bbox_union(br, it.sceneBoundingRect())
        return br

    def _gerber_scene_rect(self) -> QtCore.QRectF:
        br = QtCore.QRectF()
        for entry in self._layers:
            if not entry.pixmap_item.isVisible():
                continue
            br = _bbox_union(br, entry.pixmap_item.sceneBoundingRect())
        return br

    def _update_scene_rect_from_content(self) -> None:
        br = self._gerber_scene_rect()
        br = _bbox_union(br, self._placements_scene_rect())
        if not br.isValid():
            br = QtCore.QRectF(-10, -10, 220, 220)
        m = 5.0
        self._scene.setSceneRect(br.adjusted(-m, -m, m, m))

    def _fit_all_with_reset_view(self) -> None:
        self._view.resetTransform()
        self._fit_all_content()

    def _fit_all_content(self) -> None:
        br = self._gerber_scene_rect()
        br = _bbox_union(br, self._placements_scene_rect())
        if br.isValid():
            self._view.fitInView(br, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self._view.fitInView(self._scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def _import_kicad_mod(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "KiCad footprint", "", "KiCad (*.kicad_mod);;All (*.*)")
        if not path:
            return
        key, ok = QtWidgets.QInputDialog.getText(
            self, "Footprint key", "PnP Footprint column value this module belongs to:"
        )
        if not ok or not key.strip():
            return
        errs = self._store.import_kicad_mod(key.strip(), path)
        if errs:
            self._append_log("Import: " + "; ".join(errs))
        else:
            self._append_log(f"Imported footprint key={key!r} ← {path}")
        self.refresh_placements()

    def set_placements_from_dataframe(self, df, **kwargs) -> None:
        self._placements, warns = pcb_preview_bridge.placements_from_pnp_dataframe(df, **kwargs)
        for w in warns:
            self._append_log(w)
        self.refresh_placements()

    def refresh_placements(self) -> None:
        for it in list(self._items.values()):
            self._placements_root.removeFromGroup(it)
            self._scene.removeItem(it)
        self._items.clear()
        self._list.clear()
        for pl in self._placements:
            outline = self._store.lookup_outline(pl.footprint_name)
            if outline.source == "none" and pl.footprint_name:
                tail = pl.footprint_name.replace("\\", "/").split("/")[-1]
                outline = self._store.lookup_outline(tail)
            item = PlacementGroupItem(pl, outline)
            self._placements_root.addToGroup(item)
            self._items[pl.ref] = item
            self._list.addItem(pl.ref)
        self._set_placements_root_transform()
        self._sync_all_placement_styles()
        self._update_scene_rect_from_content()
        self._fit_all_content()

    def _on_list_selection(self) -> None:
        self._sync_all_placement_styles()

    def _center_selection(self) -> None:
        refs = [it.text() for it in self._list.selectedItems()]
        if not refs:
            return
        br = QtCore.QRectF()
        for r in refs:
            if r in self._items:
                br |= self._items[r].sceneBoundingRect()
        if br.isValid():
            self._view.fitInView(br, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    # --- Отключено вместе с UI: pick Gerber / pick Ref A–B (раньше через eventFilter на viewport) ---
    # def _on_align_toggled(self, on: bool) -> None: ...
    # def _on_pick_refs_toggled(self, on: bool) -> None: ...
    # def eventFilter(self, obj, event) -> bool: ...

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        step = self._nudge_bar.step_mm()
        if event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier:
            dx = dy = 0.0
            if event.key() == QtCore.Qt.Key.Key_Left:
                dx = -step
            elif event.key() == QtCore.Qt.Key.Key_Right:
                dx = step
            elif event.key() == QtCore.Qt.Key.Key_Up:
                dy = -step
            elif event.key() == QtCore.Qt.Key.Key_Down:
                dy = step
            if dx != 0 or dy != 0:
                refs = [it.text() for it in self._list.selectedItems()]
                if len(refs) < 1:
                    refs = list(self._items.keys())
                delta = QtCore.QPointF(dx, dy)
                for r in refs:
                    if r in self._items:
                        it = self._items[r]
                        it.setPos(it.pos() + delta)
                self._update_scene_rect_from_content()
                event.accept()
                return
        super().keyPressEvent(event)

    # def _pnp_point(self, ref: str) -> Optional[tuple[float, float]]: ...  # только для 2-point
    # def _apply_similarity(self) -> None:
    #     from pcb_preview.alignment import similarity_from_two_point_pairs
    #     ...  # см. историю git: два клика по Gerber + Ref A/B + Apply

    def _reset_transform(self) -> None:
        self._preview_sim = Similarity2D.identity()
        self._pnp_mirror_x = 1
        self._pnp_mirror_y = 1
        self._chk_mirror_x.blockSignals(True)
        self._chk_mirror_y.blockSignals(True)
        self._chk_mirror_x.setChecked(False)
        self._chk_mirror_y.setChecked(False)
        self._chk_mirror_x.blockSignals(False)
        self._chk_mirror_y.blockSignals(False)
        self._set_placements_root_transform()
        self._update_scene_rect_from_content()
        self._append_log("Preview transform reset (similarity + mirrors).")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._store.close()
        super().closeEvent(event)
