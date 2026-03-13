#!/usr/bin/env python3
"""Create an arspy algorithm scaffold from skill templates."""

import argparse
import re
import sys
from pathlib import Path

REQUIRED_TEMPLATES = {
    "app.py": "app.py.tpl",
    "app.sh": "app.sh.tpl",
    "config.py": "config.py.tpl",
    "test.json": "test.json.tpl",
    "src/main.py": "main.py.tpl",
}

DEFAULT_INPUTS = ["primaryFile", "resultPath", "auxPath"]
DEFAULT_DESCRIPTION = "基于arspy框架的新算法"


def normalize_slug(raw_name: str) -> str:
    """Normalize free-form name to a safe slug."""
    text = raw_name.strip().lower()
    text = text.replace(" ", "_")
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"[_-]{2,}", "_", text)
    text = text.strip("_-")
    if not text:
        raise ValueError("算法名称无效，规范化后为空")
    return text


def parse_inputs(raw_inputs: str) -> list[str]:
    items = [item.strip() for item in raw_inputs.split(",") if item.strip()]
    return items if items else DEFAULT_INPUTS.copy()


def default_display_name(slug: str) -> str:
    parts = [p for p in re.split(r"[_-]+", slug) if p]
    return " ".join(part.capitalize() for part in parts) if parts else slug


def render_config_inputs(input_fields: list[str]) -> str:
    lines = [f'    "{field}",' for field in input_fields]
    return "\n".join(lines)


def ensure_templates_exist(templates_dir: Path) -> None:
    missing = [name for name in REQUIRED_TEMPLATES.values() if not (templates_dir / name).exists()]
    if missing:
        raise FileNotFoundError("模板缺失: " + ", ".join(missing))


def read_template(templates_dir: Path, template_name: str) -> str:
    return (templates_dir / template_name).read_text(encoding="utf-8")


def build_replacements(slug: str, algo_name: str, description: str, input_fields: list[str]) -> dict[str, str]:
    return {
        "{{ALGORITHM_SLUG}}": slug,
        "{{ALGORITHM_NAME}}": algo_name,
        "{{ALGORITHM_DESCRIPTION}}": description,
        "{{INPUT_FIELDS_CONFIG}}": render_config_inputs(input_fields),
        "{{PRIMARY_FILE_EXAMPLE}}": f"./input/{slug}_input.dat",
        "{{RESULT_PATH_EXAMPLE}}": "./output",
        "{{AUX_PATH_EXAMPLE}}": "./aux",
        "{{RESULT_JSON_EXAMPLE}}": f"./output/{slug}_result.json",
        "{{RESULT_LOG_EXAMPLE}}": f"./output/{slug}_log.log",
        "{{RESULT_FLOW_EXAMPLE}}": f"./output/{slug}_flow.json",
    }


def render_text(text: str, replacements: dict[str, str]) -> str:
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def create_scaffold(name: str, path: Path, inputs: str, desc: str, algorithm_name: str | None, overwrite: bool, dry_run: bool) -> None:
    slug = normalize_slug(name)
    algo_name = algorithm_name.strip() if algorithm_name and algorithm_name.strip() else default_display_name(slug)
    description = desc.strip() if desc.strip() else DEFAULT_DESCRIPTION
    input_fields = parse_inputs(inputs)

    skill_root = Path(__file__).resolve().parents[1]
    templates_dir = skill_root / "assets" / "templates"
    ensure_templates_exist(templates_dir)

    target_dir = path.resolve() / slug
    if target_dir.exists() and not overwrite:
        raise FileExistsError(f"目标目录已存在: {target_dir}")

    replacements = build_replacements(slug, algo_name, description, input_fields)

    planned_files = [target_dir / rel_path for rel_path in REQUIRED_TEMPLATES]
    if dry_run:
        print(f"[DRY-RUN] 将创建目录: {target_dir}")
        for file_path in planned_files:
            print(f"[DRY-RUN] 将写入文件: {file_path}")
        return

    target_dir.mkdir(parents=True, exist_ok=overwrite)
    (target_dir / "src").mkdir(parents=True, exist_ok=True)

    for rel_path, template_name in REQUIRED_TEMPLATES.items():
        content = read_template(templates_dir, template_name)
        rendered = render_text(content, replacements)
        output_file = target_dir / rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(rendered, encoding="utf-8")

    app_sh = target_dir / "app.sh"
    app_sh.chmod(0o755)

    print(f"[OK] 已创建算法目录: {target_dir}")
    print("[OK] 运行方式: sh app.sh test.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create arspy algorithm scaffold")
    parser.add_argument("--name", required=True, help="Algorithm folder name")
    parser.add_argument("--inputs", default=",".join(DEFAULT_INPUTS), help="Comma-separated input fields")
    parser.add_argument("--desc", default=DEFAULT_DESCRIPTION, help="Algorithm description")
    parser.add_argument("--algorithm-name", default="", help="Display algorithm name; default from slug")
    parser.add_argument("--path", default=".", help="Target path where algorithm folder will be created")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing target directory")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing files")
    args = parser.parse_args()

    try:
        create_scaffold(
            name=args.name,
            path=Path(args.path),
            inputs=args.inputs,
            desc=args.desc,
            algorithm_name=args.algorithm_name,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
