import customtkinter
import tkinter
import logger
import typing

import ui_helpers

# -----------------------------------------------------------------------------

class ColumnsSelectorResult:
    def __init__(self):
        self.designator_col = ""
        self.comment_col = ""
        self.coord_x_col = ""
        self.coord_y_col = ""
        self.rotation_col = ""
        self.layer_col = ""
        self.footprint_col = ""
        self.coord_unit_mils = True
        self.has_column_headers = True

# -----------------------------------------------------------------------------

class ColumnsSelector(customtkinter.CTkToplevel):
    def __init__(self, *args, **kwargs):
        assert "app" in kwargs
        app = kwargs.pop("app")

        assert "columns" in kwargs
        columns = kwargs.pop("columns")

        assert type(columns) is list
        # logger.debug("columns: {}".format(self.columns))
        assert "callback" in kwargs
        self.callback: typing.Callable = kwargs.pop("callback")

        assert "has_column_headers" in kwargs
        has_column_headers = kwargs.pop("has_column_headers")
        assert type(has_column_headers) is bool

        # ----------

        assert "designator_default" in kwargs
        designator_default = kwargs.pop("designator_default")
        designator_default = self.__format_column(has_column_headers, columns, designator_default)

        # ----------

        assert "comment_default" in kwargs
        comment_default = kwargs.pop("comment_default")
        comment_default = self.__format_column(has_column_headers, columns, comment_default)

        # ----------

        if "footprint_default" in kwargs:
            footprint_default = kwargs.pop("footprint_default")
            footprint_default = self.__format_column(has_column_headers, columns, footprint_default)
        else:
            footprint_default = ""

# ----------
        
        # Rotation column (optional - only for PnP)
        self.show_rotation = "rotation_default" in kwargs
        if self.show_rotation:
            rotation_default = kwargs.pop("rotation_default")
            rotation_default = self.__format_column(has_column_headers, columns, rotation_default)
        else:
            rotation_default = ""
        self.rotation_default = rotation_default
        
        # ----------
        
        # optional, only for PnP
        self.show_coords = "coord_x_default" in kwargs and "coord_y_default" in kwargs and "layer_default" in kwargs
        if self.show_coords:
            coord_x_default = kwargs.pop("coord_x_default")
            coord_x_default = self.__format_column(has_column_headers, columns, coord_x_default)
            coord_y_default = kwargs.pop("coord_y_default")
            coord_y_default = self.__format_column(has_column_headers, columns, coord_y_default)
            layer_default = kwargs.pop("layer_default")
            layer_default = self.__format_column(has_column_headers, columns, layer_default)
        else:
            coord_x_default = ""
            coord_y_default = ""
            layer_default = ""

        if "coord_mils_default" in kwargs:
            coord_unit_idx = kwargs.pop("coord_mils_default")
            coord_unit_idx = 0 if coord_unit_idx else 1
        else:
            coord_unit_idx = 0 # mils

        # ----------

        super().__init__(*args, **kwargs)
        ui_helpers.window_set_centered(app, self, 450, 500)

        # prepend column titles with their corresponding index
        columns = [f"{idx+1}. {item}" for (idx,item) in enumerate(columns)]

        lbl_col_headers = customtkinter.CTkLabel(self, text="File has column headers")
        lbl_col_headers.grid(row=0, column=0, pady=5, padx=5, sticky="w")

        self.chbx_columnheaders_var = customtkinter.BooleanVar(value=has_column_headers)
        chbx_column_headers = customtkinter.CTkCheckBox(self, text="",
                                                        command=self.chbx_event, variable=self.chbx_columnheaders_var,
                                                        checkbox_width=18, checkbox_height=18)
        chbx_column_headers.grid(row=0, column=1, pady=5, padx=5, sticky="w")

        #
        lbl_designator = customtkinter.CTkLabel(self, text="Designator column:")
        lbl_designator.grid(row=1, column=0, pady=5, padx=5, sticky="w")

        self.opt_designator_var = customtkinter.StringVar(value=designator_default)
        opt_designator = customtkinter.CTkOptionMenu(self, values=columns,
                                                     command=self.opt_event,
                                                     variable=self.opt_designator_var)
        opt_designator.grid(row=1, column=1, pady=5, padx=5, sticky="we")
        self.grid_columnconfigure(1, weight=1)

        #
        lbl_comment = customtkinter.CTkLabel(self, text="Comment (value) column:")
        lbl_comment.grid(row=2, column=0, pady=5, padx=5, sticky="w")

        self.opt_comment_var = customtkinter.StringVar(value=comment_default)
        opt_comment = customtkinter.CTkOptionMenu(self, values=columns,
                                                command=self.opt_event,
                                                variable=self.opt_comment_var)
        opt_comment.grid(row=2, column=1, pady=5, padx=5, sticky="we")

        #
        lbl_footprint = customtkinter.CTkLabel(self, text="Footprint column:")
        lbl_footprint.grid(row=3, column=0, pady=5, padx=5, sticky="w")
        self.opt_footprint_var = customtkinter.StringVar(value=footprint_default)

        if footprint_default != "":
            opt_footprint = customtkinter.CTkOptionMenu(self, values=columns,
                                                    command=self.opt_event,
                                                    variable=self.opt_footprint_var)
            opt_footprint.grid(row=3, column=1, pady=5, padx=5, sticky="we")

        #
        lbl_coord_x = customtkinter.CTkLabel(self, text="X-center")
        lbl_coord_x.grid(row=4, column=0, pady=5, padx=5, sticky="w")

        self.opt_coord_x_var = customtkinter.StringVar(value=coord_x_default)
        if self.show_coords:
            opt_coord_x = customtkinter.CTkOptionMenu(self, values=columns,
                                                    command=self.opt_event,
                                                    variable=self.opt_coord_x_var)
            opt_coord_x.grid(row=4, column=1, pady=5, padx=5, sticky="we")

        #
        lbl_coord_y = customtkinter.CTkLabel(self, text="Y-center")
        lbl_coord_y.grid(row=5, column=0, pady=5, padx=5, sticky="w")

        self.opt_coord_y_var = customtkinter.StringVar(value=coord_y_default)
        if self.show_coords:
            opt_coord_y = customtkinter.CTkOptionMenu(self, values=columns,
                                                    command=self.opt_event,
                                                    variable=self.opt_coord_y_var)
            opt_coord_y.grid(row=5, column=1, pady=5, padx=5, sticky="we")

        #
        if self.show_rotation:
            lbl_rotation = customtkinter.CTkLabel(self, text="Rotation (for Merge)")
            lbl_rotation.grid(row=6, column=0, pady=5, padx=5, sticky="w")

            self.opt_rotation_var = customtkinter.StringVar(value=self.rotation_default)
            opt_rotation = customtkinter.CTkOptionMenu(self, values=columns,
                                                       command=self.opt_event,
                                                       variable=self.opt_rotation_var)
            opt_rotation.grid(row=6, column=1, pady=5, padx=5, sticky="we")

        #
        lbl_unit = customtkinter.CTkLabel(self, text="Coords unit")
        lbl_unit.grid(row=7, column=0, pady=5, padx=5, sticky="w")

        self.rb_unit_var = tkinter.IntVar(value=coord_unit_idx)

        if self.show_coords:
            #
            self.config_unit = customtkinter.CTkFrame(self)
            self.config_unit.grid(row=7, column=1, pady=5, padx=5, columnspan=1, sticky="we")
            #
            self.rb_unit_mils = customtkinter.CTkRadioButton(self.config_unit, text="mils",
                                                        variable=self.rb_unit_var,
                                                        value=0, command=self.radiobutton_unit_event)
            #
            self.rb_unit_mils.grid(row=0, column=0, pady=5, padx=5, sticky="w")
            #
            self.rb_unit_mm = customtkinter.CTkRadioButton(self.config_unit, text="mm",
                                                        variable=self.rb_unit_var,
                                                        value=1, command=self.radiobutton_unit_event)
            self.rb_unit_mm.grid(row=0, column=1, pady=5, padx=5, sticky="w")

        #
        lbl_layer = customtkinter.CTkLabel(self, text="Layer")
        lbl_layer.grid(row=9, column=0, pady=5, padx=5, sticky="w")

        self.opt_layer_var = customtkinter.StringVar(value=layer_default)
        if self.show_coords:
            opt_layer = customtkinter.CTkOptionMenu(self, values=columns,
                                                    command=self.opt_event,
                                                    variable=self.opt_layer_var)
            opt_layer.grid(row=9, column=1, pady=5, padx=5, sticky="we")

#
        sep_h = tkinter.ttk.Separator(self, orient='horizontal')
        sep_h.grid(row=10, column=0, columnspan=2, pady=5, padx=5, sticky="we",)

        self.btn_cancel = customtkinter.CTkButton(self, text="Cancel",
                                                   command=self.button_cancel_event)
        #
        self.btn_cancel.grid(row=11, column=0, pady=10, padx=5, sticky="")

        self.btn_ok = customtkinter.CTkButton(self, text="OK",
                                                  command=self.button_ok_event)
        self.btn_ok.grid(row=11, column=1, pady=10, padx=5, sticky="we")
        self.btn_ok.configure(state=tkinter.DISABLED)

        # Initialize rotation var if not shown (for BOM selector)
        if not self.show_rotation:
            self.opt_rotation_var = customtkinter.StringVar(value="")

        # enable "always-on-top" for this popup window
        self.attributes('-topmost', True)

    def __format_column(self, has_headers: bool, columns: list[str], col_default) -> str:
        if has_headers:
            # prepend column title with its index
            try:
                default_idx = columns.index(col_default)
            except ValueError as e:
                default_idx = 0
            col_default = f"{default_idx+1}. {col_default}"
        else:
            # designator is a column index
            if type(col_default) is not int:
                col_default = 0
                # raise ValueError(f"Column selector: if no headers, column id '{col_default}' must be an int")
            col_default = f"{col_default+1}. {columns[col_default]}"

        return col_default

    def chbx_event(self):
        self.btn_ok.configure(state=tkinter.NORMAL)

    def opt_event(self, _new_choice: str):
        if self.opt_designator_var.get() != "" and self.opt_comment_var.get() != "":
            self.btn_ok.configure(state=tkinter.NORMAL)

    def radiobutton_unit_event(self):
        self.btn_ok.configure(state=tkinter.NORMAL)

    def button_cancel_event(self):
        logger.info("Column selector: cancelled")
        self.destroy()

    def button_ok_event(self):
        result = ColumnsSelectorResult()

        result.has_column_headers = self.chbx_columnheaders_var.get()
        result.designator_col = self.opt_designator_var.get()
        result.comment_col = self.opt_comment_var.get()
        result.coord_x_col = self.opt_coord_x_var.get()
        result.coord_y_col = self.opt_coord_y_var.get()
        result.rotation_col = self.opt_rotation_var.get()
        result.coord_unit_mils = self.rb_unit_var.get() == 0
        result.layer_col = self.opt_layer_var.get()
        result.footprint_col = self.opt_footprint_var.get()

        if result.has_column_headers:
            result.designator_col = result.designator_col.split(sep=". ")[1]
            result.comment_col = result.comment_col.split(sep=". ")[1]
            if (result.footprint_col):
                result.footprint_col = result.footprint_col.split(sep=". ")[1]
            if (result.rotation_col):
                result.rotation_col = result.rotation_col.split(sep=". ")[1]
            if self.show_coords:
                result.coord_x_col = result.coord_x_col.split(sep=". ")[1]
                result.coord_y_col = result.coord_y_col.split(sep=". ")[1]
                result.layer_col = result.layer_col.split(sep=". ")[1]
        else:
            # numeric index (0-based)
            result.designator_col = int(result.designator_col.split(sep=". ")[0])
            result.designator_col -= 1
            result.comment_col = int(result.comment_col.split(sep=". ")[0])
            result.comment_col -= 1
            if result.footprint_col:
                result.footprint_col = int(result.footprint_col.split(sep=". ")[0])
                result.footprint_col -= 1
            if result.rotation_col:
                result.rotation_col = int(result.rotation_col.split(sep=". ")[0])
                result.rotation_col -= 1
            if self.show_coords:
                result.coord_x_col = int(result.coord_x_col.split(sep=". ")[0])
                result.coord_x_col -= 1
                result.coord_y_col = int(result.coord_y_col.split(sep=". ")[0])
                result.coord_y_col -= 1
                result.layer_col = int(result.layer_col.split(sep=". ")[0])
                result.layer_col -= 1
        self.callback(result)
        self.destroy()
