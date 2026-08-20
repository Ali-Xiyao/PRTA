from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "paper"
    output = root / "data" / "07_论文材料清单与哈希.md"
    files = sorted(
        path
        for path in root.rglob("*")
        if path.suffix in {".json", ".md"} and path.resolve() != output.resolve()
    )
    lines = [
        "# 论文材料清单与 SHA256",
        "",
        f"生成日期：{date.today().isoformat()}（Asia/Shanghai）。",
        "",
        "本表用于把整个 `paper/` 复制到另一台电脑后核验材料是否完整。哈希覆盖",
        "除本清单自身之外的全部 Markdown/JSON 文件；字节数与 SHA256 均按原始字节",
        "计算。本目录不包含患者级预测、checkpoint、影像或受保护测试集结果。",
        "",
        "| 文件 | 字节数 | SHA256 |",
        "|---|---:|---|",
    ]
    for path in files:
        relative = path.relative_to(root).as_posix()
        lines.append(f"| `{relative}` | {path.stat().st_size:,} | `{_sha256(path)}` |")
    lines.extend(
        [
            "",
            "核验示例（PowerShell）：",
            "",
            "```powershell",
            "Get-FileHash -Algorithm SHA256 .\\paper\\README.md",
            "```",
            "",
            "原始运行证据自身的哈希见 [证据来源与哈希](04_证据来源与哈希.md)。",
            "",
        ]
    )
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(output)
    print(f"PASS_PAPER_INVENTORY_REFRESHED files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
