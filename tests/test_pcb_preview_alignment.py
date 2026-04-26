"""Tests for pcb_preview similarity (no Qt)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pcb_preview.alignment import Similarity2D, similarity_from_two_point_pairs


def test_similarity_maps_landmarks() -> None:
    p1 = (0.0, 0.0)
    p2 = (10.0, 0.0)
    g1 = (100.0, 200.0)
    g2 = (100.0, 210.0)
    sim = similarity_from_two_point_pairs(p1, p2, g1, g2)
    a = sim.apply(*p1)
    b = sim.apply(*p2)
    assert abs(a[0] - g1[0]) < 1e-6 and abs(a[1] - g1[1]) < 1e-6
    assert abs(b[0] - g2[0]) < 1e-6 and abs(b[1] - g2[1]) < 1e-6


def test_similarity_rotation_90() -> None:
    p1 = (0.0, 0.0)
    p2 = (1.0, 0.0)
    g1 = (0.0, 0.0)
    g2 = (0.0, 1.0)
    sim = similarity_from_two_point_pairs(p1, p2, g1, g2)
    x, y = sim.apply(1.0, 0.0)
    assert abs(x - 0.0) < 1e-5 and abs(y - 1.0) < 1e-5


def test_identity_degenerate() -> None:
    sim = similarity_from_two_point_pairs((0, 0), (0, 0), (1, 1), (2, 2))
    assert isinstance(sim, Similarity2D)
    assert sim.scale == pytest.approx(1.0)
