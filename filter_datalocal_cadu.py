from pathlib import Path
import filecmp
import re
import shutil
import tempfile
import uuid


DATA_LOCAL = Path(__file__).resolve().parent / "dataLocal"
YEAR_DIR_PATTERN = re.compile(r"^2026(?: \(\d+\))?$")
TIME_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_")


def find_sources() -> list[tuple[Path, Path]]:
    """Return (original folder, folder whose relative structure should be kept)."""
    sources = []

    for folder in sorted(DATA_LOCAL.iterdir()):
        if not folder.is_dir() or not YEAR_DIR_PATTERN.fullmatch(folder.name):
            continue

        # Drive downloads such as "2026 (1)" contain an extra "2026" folder.
        content_root = folder / "2026" if folder.name != "2026" and (folder / "2026").is_dir() else folder
        sources.append((folder, content_root))

    return sources


def collect_cadu_files(sources: list[tuple[Path, Path]]) -> dict[Path, Path]:
    """Map each preserved relative path to its source file; reject conflicting duplicates."""
    files: dict[Path, Path] = {}

    for _, content_root in sources:
        for source_file in content_root.rglob("*"):
            if not source_file.is_file() or source_file.suffix.lower() != ".cadu":
                continue

            relative_path = source_file.relative_to(content_root)
            previous = files.get(relative_path)
            if previous is not None:
                if not filecmp.cmp(previous, source_file, shallow=False):
                    raise ValueError(f"Hai file .cadu trùng đường dẫn nhưng khác nội dung: {relative_path}")
                continue

            files[relative_path] = source_file

    return files


def validate_one_cadu_per_time_folder(
    sources: list[tuple[Path, Path]], cadu_files: dict[Path, Path]
) -> None:
    time_folders = {
        folder.name
        for _, content_root in sources
        for folder in content_root.iterdir()
        if folder.is_dir() and TIME_DIR_PATTERN.match(folder.name)
    }

    cadu_counts: dict[str, int] = {}
    for relative_path in cadu_files:
        if not relative_path.parts or not TIME_DIR_PATTERN.match(relative_path.parts[0]):
            raise ValueError(f"File .cadu tidak nằm trong folder thời gian: {relative_path}")
        time_folder = relative_path.parts[0]
        cadu_counts[time_folder] = cadu_counts.get(time_folder, 0) + 1

    missing = sorted(time_folders - cadu_counts.keys())
    multiple = sorted(folder for folder, count in cadu_counts.items() if count != 1)
    if missing or multiple:
        details = []
        if missing:
            details.append(f"folder không có file .cadu: {', '.join(missing[:5])}")
        if multiple:
            details.append(f"folder có nhiều file .cadu: {', '.join(multiple[:5])}")
        raise ValueError("; ".join(details))


def main() -> None:
    if not DATA_LOCAL.is_dir():
        print(f"Không tìm thấy thư mục: {DATA_LOCAL}")
        return

    sources = find_sources()
    if not sources:
        print("Không tìm thấy thư mục 2026 nào trong DataLocal.")
        return

    try:
        cadu_files = collect_cadu_files(sources)
        validate_one_cadu_per_time_folder(sources, cadu_files)
    except ValueError as error:
        print(f"Không thể lọc an toàn: {error}")
        return
    total_files = sum(
        1
        for _, content_root in sources
        for path in content_root.rglob("*")
        if path.is_file()
    )
    total_cadu = sum(
        1
        for _, content_root in sources
        for path in content_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".cadu"
    )

    print(f"Thư mục nguồn: {', '.join(folder.name for folder, _ in sources)}")
    print(f"Sẽ giữ {len(cadu_files)} file .cadu trong DataLocal/2026.")
    print(f"Sẽ loại {total_files - total_cadu} file không phải .cadu.")
    print("Cấu trúc và tên các thư mục thời gian sẽ được giữ nguyên.")
    print("Mỗi folder thời gian sẽ còn đúng 1 file .cadu và không còn file khác.")
    print("Các thư mục 2026 tải trùng sẽ được gộp vào 2026 rồi xóa sau khi gộp thành công.")

    if input('Nhập "yes" để xác nhận gộp và lọc: ').strip().lower() != "yes":
        print("Đã hủy.")
        return

    staging_dir = Path(tempfile.mkdtemp(prefix=".2026_cadu_stage_", dir=DATA_LOCAL))
    backups: list[tuple[Path, Path]] = []

    try:
        # Keep the folder structure, but omit empty MSU-MR image folders.
        for _, content_root in sources:
            for source_dir in content_root.rglob("*"):
                if source_dir.is_dir():
                    relative_dir = source_dir.relative_to(content_root)
                    if any(part.casefold() == "msu-mr" for part in relative_dir.parts):
                        continue
                    (staging_dir / relative_dir).mkdir(parents=True, exist_ok=True)

        for relative_path, source_file in cadu_files.items():
            destination = staging_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)

        copied_count = sum(1 for path in staging_dir.rglob("*") if path.is_file())
        if copied_count != len(cadu_files):
            raise RuntimeError("Số file trong thư mục tạm không khớp; dữ liệu nguồn được giữ nguyên.")
        if any(path.is_file() and path.suffix.lower() != ".cadu" for path in staging_dir.rglob("*")):
            raise RuntimeError("Thư mục tạm có file không phải .cadu; dữ liệu nguồn được giữ nguyên.")

        # Move the source folders aside, then promote the completed clean tree.
        for source_folder, _ in sources:
            backup = DATA_LOCAL / f".{source_folder.name}.backup_{uuid.uuid4().hex}"
            source_folder.rename(backup)
            backups.append((source_folder, backup))

        staging_dir.rename(DATA_LOCAL / "2026")
    except Exception as error:
        for source_folder, backup in reversed(backups):
            if backup.exists() and not source_folder.exists():
                backup.rename(source_folder)
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        print(f"Không hoàn tất được thao tác: {error}")
        return

    leftovers = []
    for _, backup in backups:
        try:
            shutil.rmtree(backup)
        except OSError:
            leftovers.append(backup)

    print(f"Hoàn tất: DataLocal/2026 hiện có {copied_count} file .cadu.")
    if leftovers:
        print("Không xóa được một số thư mục nguồn cũ:")
        for path in leftovers:
            print(f"  {path}")


if __name__ == "__main__":
    main()
