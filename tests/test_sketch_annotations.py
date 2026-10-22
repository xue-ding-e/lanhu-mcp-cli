"""Regression coverage for annotations omitted from imported Figma designs."""

import copy
import json
from pathlib import Path

import pytest

from lanhu_cli import _extract_elements
from lanhu_mcp_server import convert_sketch_to_html


@pytest.fixture
def figma_design():
    fixture = Path(__file__).parent / "fixtures" / "figma_shipping_annotations.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def convert(design):
    html, _, annotations = convert_sketch_to_html(design)
    return html, {item["name"]: item["css"] for item in annotations}


def test_real_figma_pixel_and_auto_line_height_reach_cli(figma_design):
    html, annotations = convert(figma_design)
    elements = {item["name"]: item["css"] for item in _extract_elements([html])}

    assert annotations["发货"]["line-height"] == "56rpx"
    assert elements["发货"]["line-height"] == "56rpx"
    assert annotations["￥"]["line-height"] == "normal"
    assert elements["￥"]["line-height"] == "normal"
    assert "line-height:56px" in html
    assert "line-height:normal" in html


def test_real_figma_path_radius_overrides_zero_layer_radius(figma_design):
    _, annotations = convert(figma_design)

    assert annotations["Rectangle 727"]["border-radius"] == "16rpx"


def test_figma_corner_order_is_clockwise(figma_design):
    shape = figma_design["artboard"]["layers"][2]
    # Distinct corners expose the source dictionary's BL/BR insertion order.
    shape["paths"][0]["radius"] = {
        "topLeft": 1, "topRight": 2, "bottomLeft": 3, "bottomRight": 4
    }

    _, annotations = convert(figma_design)

    assert annotations["Rectangle 727"]["border-radius"] == "2rpx 4rpx 8rpx 6rpx"


def test_explicit_zero_figma_path_radius_is_authoritative(figma_design):
    shape = figma_design["artboard"]["layers"][2]
    shape["paths"][0]["radius"] = dict.fromkeys(shape["radius"], 0)
    shape["radius"] = dict.fromkeys(shape["radius"], 8)

    _, annotations = convert(figma_design)

    assert "border-radius" not in annotations["Rectangle 727"]


def test_figma_layer_radius_is_used_without_path_radius(figma_design):
    shape = figma_design["artboard"]["layers"][2]
    shape["paths"] = []
    shape["radius"] = {"topLeft": 1, "topRight": 2, "bottomLeft": 3, "bottomRight": 4}

    _, annotations = convert(figma_design)

    assert annotations["Rectangle 727"]["border-radius"] == "2rpx 4rpx 8rpx 6rpx"


def test_figma_percent_line_height_keeps_its_unit(figma_design):
    font = figma_design["artboard"]["layers"][0]["text"]["style"]["font"]
    font["lineHeight"] = {"unit": "PERCENT", "value": 150}

    html, annotations = convert(figma_design)

    assert annotations["发货"]["line-height"] == "150%"
    assert "line-height:150%" in html


@pytest.mark.parametrize(
    ("text_info", "height", "expected"),
    [
        ({"leading": 21}, 60, "42rpx"),
        ({"lineHeight": {"value": 24}}, 60, "48rpx"),
        ({"text": "first\rsecond"}, 60, "60.0rpx"),
        ({}, 20, "1"),
    ],
)
def test_sketch_line_height_preserves_rendered_value(text_info, height, expected):
    layer = {
        "name": "legacy text", "type": "textLayer", "width": 100, "height": height,
        "textInfo": {"text": "legacy", "size": 14, **text_info},
    }

    html, annotations = convert({"board": {"width": 375, "height": 667, "layers": [layer]}})

    assert annotations["legacy text"]["line-height"] == expected
    assert "line-height:" + expected.replace("rpx", "px") in html


def test_sketch_path_radius_keeps_existing_format(figma_design):
    shape = copy.deepcopy(figma_design["artboard"]["layers"][2])
    shape.pop("paths")
    shape["path"] = {"pathComponents": [{"origin": {"radii": [1, 2, 3, 4]}}]}

    _, annotations = convert({"board": {"width": 375, "height": 667, "layers": [
        {**shape, "width": 343, "height": 221}
    ]}})

    assert annotations["Rectangle 727"]["border-radius"] == "2rpx 4rpx 6rpx 8rpx"
