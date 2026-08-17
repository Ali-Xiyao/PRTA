from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prta_cxr.contracts import sha256_file
from prta_cxr.slim_matrix import SLIM_ARMS


def _closed(value: Mapping[str, Any]) -> None:
    if value.get("status") != "PASS_SLIM_MATRIX_SELECTED":
        raise ValueError("Slim result is not terminal PASS")
    if value.get("selection_performed") is not True:
        raise ValueError("Slim result lacks frozen selection")
    if value.get("winner_selected") is not True:
        raise ValueError("Slim result lacks a winner")
    if value.get("selected_arm") not in SLIM_ARMS:
        raise ValueError("Slim result selected an unknown arm")
    for key in (
        "current_dev_used_for_selection",
        "internal_test_opened",
        "gold_opened",
        "external_opened",
    ):
        if value.get(key) is not False:
            raise ValueError(f"Slim result reports forbidden access: {key}")
    if value.get("protected_outcome_read_count") != 0:
        raise ValueError("Slim result reports protected reads")


def _audit_export_surface(value: object, *, path: str = "root") -> None:
    forbidden_keys = {
        "patient_id",
        "patient_id_hash",
        "sample_id",
        "checkpoint_path",
        "prediction_path",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in forbidden_keys:
                raise ValueError(f"Slim export contains forbidden key: {path}.{key}")
            _audit_export_surface(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _audit_export_surface(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if "/ipfs/" in lowered or ":\\" in value or "file://" in lowered:
            raise ValueError(f"Slim export contains an absolute path: {path}")


def render_slim_narrative(value: Mapping[str, Any]) -> str:
    selected = str(value["selected_arm"])
    prototype, state = SLIM_ARMS[selected]
    factors = []
    if prototype:
        factors.append("standalone prototype CE")
    if state:
        factors.append("state anchor")
    optional = "、".join(factors) if factors else "不保留这两个可选辅助目标"
    return "\n".join(
        [
            "# PRTA-CXR-Slim 最终方法叙事",
            "",
            (
                f"Train-only 冻结规则选择了 `{selected}`，判定为 "
                f"`{value['selection_disposition']}`。"
            ),
            "",
            "## 最终结构",
            "",
            (
                "最终候选固定保留 finding-guided conditioning、cross-time "
                "alignment、temporal relation residual、ODC 与 matched-hard "
                "CMCP；DMW 固定删除。"
            ),
            "",
            f"在 prototype CE × state anchor 的 2×2 中，最终配置{optional}。",
            "",
            "## 论文表述边界",
            "",
            "- 该选择只使用原 Train 患者派生的 patient-disjoint Slim-Dev。",
            "- 原 Dev、Internal-test、Gold、外部数据均未参与本轮选择。",
            "- 历史 V2、完整消融与失败尝试继续保留为方法开发和附录证据。",
            "- 当前结论是内部 Train-only 非劣精简结论，不等同于外部泛化验证。",
            "",
            "## 冻结损失叙事",
            "",
            (
                "主线保持为：找对 finding、比较对历史、避免反方向错误。"
                "后续测试只能评估冻结候选，不能再根据结果修改模块或容差。"
            ),
            "",
        ]
    )


def export_slim_results(
    *, final_json: Path, final_markdown: Path, repo_root: Path
) -> dict[str, Any]:
    value = json.loads(final_json.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Slim final JSON must be an object")
    _closed(value)
    _audit_export_surface(value)
    markdown = final_markdown.read_text(encoding="utf-8")
    for forbidden in ("/ipfs/", "file://", ":\\"):
        if forbidden.lower() in markdown.lower():
            raise ValueError("Slim Markdown contains an absolute path")
    data_root = repo_root / "paper" / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    output_json = data_root / "12_PRTA-CXR-Slim最小矩阵结果.json"
    output_markdown = data_root / "12_PRTA-CXR-Slim最小矩阵结果.md"
    narrative = repo_root / "paper" / "09_PRTA-CXR-Slim最终叙事_CN.md"
    outputs = {
        output_json: json.dumps(value, indent=2, sort_keys=True) + "\n",
        output_markdown: markdown.rstrip() + "\n",
        narrative: render_slim_narrative(value),
    }
    for path in outputs:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite Slim paper artifact: {path}")
    for path, text in outputs.items():
        temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    return {
        "status": "PASS_SLIM_RESULTS_EXPORTED",
        "selected_arm": value["selected_arm"],
        "outputs": {
            str(path.relative_to(repo_root)).replace("\\", "/"): sha256_file(path)
            for path in outputs
        },
        "protected_outcome_read_count": 0,
    }


def export_slim_results_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export safe Slim paper artifacts")
    parser.add_argument("--final-json", type=Path, required=True)
    parser.add_argument("--final-markdown", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    result = export_slim_results(
        final_json=args.final_json,
        final_markdown=args.final_markdown,
        repo_root=args.repo_root,
    )
    if args.receipt.exists():
        raise FileExistsError(f"refusing existing export receipt: {args.receipt}")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
