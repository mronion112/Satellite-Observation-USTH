from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "dataWeb"


def main() -> None:
    if not DATA_DIR.is_dir():
        print(f"Không tìm thấy thư mục: {DATA_DIR}")
        return

    files_to_delete = [
        path
        for path in DATA_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() != ".cadu"
    ]

    print(f"Sẽ xóa {len(files_to_delete)} file trong {DATA_DIR}.")
    print("Các thư mục sẽ được giữ nguyên.")

    if input('Nhập "yes" để xác nhận xóa: ').strip().lower() != "yes":
        print("Đã hủy.")
        return

    for path in files_to_delete:
        path.unlink()

    print("Đã xóa xong.")


if __name__ == "__main__":
    main()
