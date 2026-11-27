"""ZipBackup: создание zip-архивов с манифестом и git-подобная сверка структуры."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime
from fnmatch import fnmatch

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    "__pycache__", "*.pyc", "*.pyo", "*.pyd",
    ".ipynb_checkpoints",
    ".git", ".gitignore", ".gitattributes", ".gitmodules",
    ".venv", "venv", "env", ".env", "ENV",
    ".idea", ".vscode", ".vs",
    "dist", "build", "*.whl", "*.egg",
)

_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_BLUE = "\033[34m"
_RESET = "\033[0m"


class ZipBackup:
    """Бэкап файлов в zip + git-подобная сверка структуры по манифесту."""

    DEFAULT_IGNORE_PATTERNS = DEFAULT_IGNORE_PATTERNS

    # ===================== хелперы =====================

    @staticmethod
    def _norm(p) -> str:
        """Каноничный путь для сравнения. НЕ ломает '../'."""
        return os.path.normpath(os.fspath(p)).replace("\\", "/")

    @staticmethod
    def _arc_root(item) -> str:
        n = os.path.normpath(os.fspath(item))
        return "" if n == "." else os.path.basename(n)

    @staticmethod
    def _join(cur: str, name: str) -> str:
        return f"{cur}/{name}" if cur else name

    @staticmethod
    def _sha256(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _is_inside(path, dirs) -> bool:
        p = os.path.normpath(path)
        for d in dirs:
            dp = os.path.normpath(d)
            if p == dp or p.startswith(dp + os.sep):
                return True
        return False

    # ===================== create_zip =====================

    def create_zip(
        self,
        zip_filename,
        items,
        exclusions=None,
        ignore_patterns=None,
        manifest_filename=None,
    ) -> None:
        """Создать zip-архив и рядом — манифест с отпечатками файлов."""
        patterns = list(ignore_patterns) if ignore_patterns is not None else list(self.DEFAULT_IGNORE_PATTERNS)
        excl_set = {self._norm(e) for e in (exclusions or []) if self._norm(e) and self._norm(e) != "."}

        dedup_items = self._dedup_items(items, excl_set)

        if manifest_filename is None:
            manifest_filename = os.fspath(zip_filename) + ".manifest.json"

        def is_ignored(arc: str) -> bool:
            return any(
                fnmatch(part, pat) or fnmatch(arc, pat)
                for part in arc.split("/")
                for pat in patterns
            )

        def is_excluded(arc: str, rel: str) -> bool:
            return any(
                arc == e or arc.startswith(e + "/") or
                rel == e or rel.startswith(e + "/")
                for e in excl_set
            )

        m_items, m_files, m_dirs, m_excluded = [], [], [], []
        seen_arc, seen_src = set(), set()

        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zf:
            for raw in dedup_items:
                item = os.path.normpath(os.fspath(raw))
                if not os.path.exists(item) or os.path.islink(item):
                    continue

                prefix = self._arc_root(item)
                abs_item = os.path.abspath(item)
                m_items.append({"abs_path": abs_item, "arc_root": prefix})

                if os.path.isfile(item):
                    arc = os.path.basename(item)
                    if is_ignored(arc):
                        continue
                    if is_excluded(arc, arc):
                        m_excluded.append({"arcname": arc, "kind": "file", "abs_path": abs_item})
                        continue
                    src = os.path.realpath(item)
                    if src in seen_src or arc in seen_arc:
                        continue
                    zf.write(item, arc)
                    seen_src.add(src); seen_arc.add(arc)
                    m_files.append({
                        "arcname": arc, "abs_path": abs_item,
                        "size": os.path.getsize(item),
                        "sha256": self._sha256(item),
                    })
                    continue

                if os.path.isdir(item) and not (is_ignored(prefix) or is_excluded(prefix, prefix)):
                    for root_dir, dirs, files in os.walk(item):
                        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root_dir, d))]

                        rel = os.path.relpath(root_dir, item)
                        rel = "" if rel == "." else rel.replace(os.sep, "/")
                        cur = prefix if not rel else self._join(prefix, rel)

                        kept = []
                        for d in dirs:
                            sub_arc = self._join(cur, d)
                            sub_rel = self._join(rel, d)
                            full = os.path.join(root_dir, d)
                            if is_ignored(sub_arc):
                                continue
                            if is_excluded(sub_arc, sub_rel):
                                m_excluded.append({"arcname": sub_arc, "kind": "dir", "abs_path": full})
                                continue
                            kept.append(d)
                        dirs[:] = kept

                        if cur and cur not in seen_arc:
                            zf.writestr(cur + "/", "")
                            seen_arc.add(cur)
                            m_dirs.append({"arcname": cur, "abs_path": root_dir})

                        for f in files:
                            fpath = os.path.join(root_dir, f)
                            if os.path.islink(fpath):
                                continue
                            ap = self._join(cur, f)
                            ar = self._join(rel, f)
                            if is_ignored(ap):
                                continue
                            if is_excluded(ap, ar):
                                m_excluded.append({"arcname": ap, "kind": "file", "abs_path": fpath})
                                continue
                            src = os.path.realpath(fpath)
                            if src in seen_src or ap in seen_arc:
                                continue
                            zf.write(fpath, ap)
                            seen_src.add(src); seen_arc.add(ap)
                            m_files.append({
                                "arcname": ap, "abs_path": fpath,
                                "size": os.path.getsize(fpath),
                                "sha256": self._sha256(fpath),
                            })

        manifest = {
            "version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "zip_filename": os.path.basename(os.fspath(zip_filename)),
            "items": m_items,
            "exclusions": sorted(excl_set),
            "ignore_patterns": patterns,
            "default_ignore_patterns": list(self.DEFAULT_IGNORE_PATTERNS),
            "files": m_files,
            "dirs": m_dirs,
            "excluded_entries": m_excluded,
        }
        with open(manifest_filename, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # ===================== check_structure =====================

    def check_structure(self, manifest_filename, ignore_patterns=None) -> None:
        """Сравнить текущую ФС с состоянием в манифесте. Печатает DELETED/MODIFIED/ADDED/RENAMED."""
        with open(manifest_filename, "r", encoding="utf-8") as f:
            m = json.load(f)

        patterns = list(m.get("ignore_patterns") or self.DEFAULT_IGNORE_PATTERNS)
        if ignore_patterns:
            patterns = list(ignore_patterns)

        ref_files = {e["arcname"]: e for e in m.get("files", [])}
        ref_dirs = {e["arcname"]: e["abs_path"] for e in m.get("dirs", [])}
        excl_paths = {e["abs_path"] for e in m.get("excluded_entries", [])}
        excl_dirs = {e["abs_path"] for e in m.get("excluded_entries", []) if e.get("kind") == "dir"}

        def is_ignored(arc: str) -> bool:
            return any(
                fnmatch(part, pat) or fnmatch(arc, pat)
                for part in arc.split("/")
                for pat in patterns
            )

        cur_files, cur_dirs = {}, {}

        for item_entry in m.get("items", []):
            abs_item = item_entry["abs_path"]
            prefix = item_entry["arc_root"]

            if not os.path.exists(abs_item) or os.path.islink(abs_item):
                continue

            if os.path.isfile(abs_item):
                arc = os.path.basename(abs_item)
                if is_ignored(arc) or abs_item in excl_paths:
                    continue
                try:
                    sha = self._sha256(abs_item)
                except OSError:
                    continue
                cur_files[arc] = {"abs_path": abs_item, "size": os.path.getsize(abs_item), "sha256": sha}
                continue

            if os.path.isdir(abs_item):
                for root_dir, dirs, files in os.walk(abs_item):
                    dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root_dir, d))]

                    rel = os.path.relpath(root_dir, abs_item)
                    rel = "" if rel == "." else rel.replace(os.sep, "/")
                    cur = prefix if not rel else self._join(prefix, rel)

                    kept = []
                    for d in dirs:
                        full = os.path.join(root_dir, d)
                        sub_arc = self._join(cur, d)
                        if is_ignored(sub_arc):
                            continue
                        if self._is_inside(full, excl_dirs):
                            continue
                        kept.append(d)
                    dirs[:] = kept

                    if cur and cur not in cur_dirs:
                        if not is_ignored(cur) and not self._is_inside(root_dir, excl_dirs):
                            cur_dirs[cur] = root_dir

                    for f in files:
                        fpath = os.path.join(root_dir, f)
                        if os.path.islink(fpath):
                            continue
                        ap = self._join(cur, f)
                        if is_ignored(ap):
                            continue
                        if self._is_inside(fpath, excl_dirs) or fpath in excl_paths:
                            continue
                        try:
                            sha = self._sha256(fpath)
                        except OSError:
                            continue
                        cur_files[ap] = {"abs_path": fpath, "size": os.path.getsize(fpath), "sha256": sha}

        deleted, modified, added = [], [], []
        for arc, ref in ref_files.items():
            if arc not in cur_files:
                deleted.append((arc, "file"))
            elif cur_files[arc]["sha256"] != ref["sha256"]:
                modified.append(arc)
        for arc in cur_files:
            if arc not in ref_files:
                added.append((arc, "file"))
        for arc in ref_dirs:
            if arc not in cur_dirs:
                deleted.append((arc, "dir"))
        for arc in cur_dirs:
            if arc not in ref_dirs:
                added.append((arc, "dir"))

        renamed = []
        del_sha = {ref_files[a]["sha256"]: a for a, t in deleted if t == "file"}
        used_d, used_a = set(), set()
        for ap, t in added:
            if t != "file":
                continue
            sha = cur_files[ap]["sha256"]
            if sha in del_sha:
                renamed.append((del_sha[sha], ap))
                used_d.add(del_sha[sha])
                used_a.add(ap)
        deleted = [(a, t) for a, t in deleted if not (t == "file" and a in used_d)]
        added = [(a, t) for a, t in added if not (t == "file" and a in used_a)]

        self._print_report(deleted, modified, added, renamed)

    # ===================== внутренние =====================

    def _dedup_items(self, items, excl_set):
        """Объединить дубликаты: под-пути поглощаются родителями.
        exclusions важнее: если item целиком в exclusions — убрать.
        """
        norm = []
        for i in items:
            n = self._norm(i)
            norm.append(n if n not in ("", "./") else ".")

        seen, uniq = set(), []
        for n in norm:
            if n not in seen:
                seen.add(n); uniq.append(n)

        if "." in uniq:
            uniq = [n for n in uniq if os.path.isabs(n)]
            uniq.insert(0, ".")

        kept = []
        for n in uniq:
            base = os.path.basename(n) if n != "." else ""
            if n in excl_set or base in excl_set:
                continue
            kept.append(n)

        result = []
        for n in kept:
            absorbed = any(
                m != n and (
                    (m == "." and not os.path.isabs(n)) or
                    n.startswith(m + "/")
                )
                for m in kept
            )
            if not absorbed:
                result.append(n)
        return result

    def _print_report(self, deleted, modified, added, renamed):
        def fmt(arc, kind):
            tag = "[dir] " if kind == "dir" else ""
            return f"  {tag}{arc}"

        if deleted:
            print(f"{_RED}DELETED ({len(deleted)}):{_RESET}")
            for arc, kind in sorted(deleted):
                print(f"{_RED}{fmt(arc, kind)}{_RESET}")
        if modified:
            print(f"{_YELLOW}MODIFIED ({len(modified)}):{_RESET}")
            for arc in sorted(modified):
                print(f"{_YELLOW}  {arc}{_RESET}")
        if added:
            print(f"{_GREEN}ADDED ({len(added)}):{_RESET}")
            for arc, kind in sorted(added):
                print(f"{_GREEN}{fmt(arc, kind)}{_RESET}")
        if renamed:
            print(f"{_BLUE}RENAMED ({len(renamed)}):{_RESET}")
            for old, new in sorted(renamed):
                print(f"{_BLUE}  {old} -> {new}{_RESET}")
        if not (deleted or modified or added or renamed):
            print(f"{_GREEN}Структура не изменилась с момента последнего бэкапа.{_RESET}")


__all__ = ["ZipBackup", "DEFAULT_IGNORE_PATTERNS"]
