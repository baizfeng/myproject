---
name: windows-path-to-linux-mnt
description: Convert Windows-style paths to Linux WSL mount paths and normalize mixed separators. Use when a user provides paths like `C:\\...`, `D:/...`, or drive-rooted absolute paths and expects Linux-compatible paths such as `/mnt/c/...`.
---

# Windows Path To Linux Mnt

Normalize incoming filesystem paths into Linux paths under `/mnt/<drive-letter>/...`.

## Workflow

1. Detect Windows absolute path patterns.
- Match drive-letter forms such as `C:\\foo\\bar` and `D:/foo/bar`.
- Keep non-Windows paths unchanged.

2. Convert to Linux mount path.
- Lowercase the drive letter.
- Replace `\\` with `/`.
- Strip a leading `/` from the remainder after the drive marker if present.
- Build output as `/mnt/<drive>/<rest>`.

3. Preserve meaningful characters.
- Preserve spaces and UTF-8 characters in path segments.
- Trim surrounding single or double quotes only when they wrap the whole path.

## Quick Rules

- `H:\\water\\shandong\\chenqinghui\\code\\water` -> `/mnt/h/water/shandong/chenqinghui/code/water`
- `C:/Users/Alice/project` -> `/mnt/c/Users/Alice/project`
- `/home/alice/project` -> unchanged

## Resources

### scripts/

Use `scripts/convert_path.py` for deterministic conversion.

Examples:

```bash
python3 scripts/convert_path.py 'H:\\water\\shandong\\chenqinghui\\code\\water'
python3 scripts/convert_path.py 'C:/Users/Alice/project'
```
