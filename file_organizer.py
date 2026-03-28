import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import mimetypes
from datetime import datetime
from PIL import Image

# ==================== 辅助函数 ====================
def get_year(file_path):
    if get_base_category(file_path) == "images":
        try:
            with Image.open(file_path) as img:
                exif = img._getexif() or {}
                exif_time = exif.get(36867) or exif.get(306)
                if exif_time:
                    dt = datetime.strptime(exif_time, "%Y:%m:%d %H:%M:%S")
                    return str(dt.year)
        except Exception:
            pass
    try:
        return str(datetime.fromtimestamp(os.path.getmtime(file_path)).year)
    except Exception:
        return "未知年份"


def is_photo_with_exif(file_path):
    try:
        with Image.open(file_path) as img:
            exif = img._getexif() or {}
            return bool(exif.get(36867) or exif.get(306))
    except Exception:
        return False


def get_base_category(file_path):
    ext = Path(file_path).suffix.lower()
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        main = mime_type.split('/')[0]
        if main == 'image': return "images"
        if main == 'video': return "videos"
        if main == 'audio': return "audios"
        if main in ('text', 'application') or any(x in mime_type for x in ['pdf', 'document']):
            return "documents"
    if ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt'): return "documents"
    if ext in ('.mp4', '.mov', '.mkv', '.avi', '.wmv'): return "videos"
    if ext in ('.mp3', '.wav', '.flac', '.m4a', '.aac'): return "audios"
    if ext in ('.zip', '.rar', '.7z'): return "archives"
    return "other"


def get_detailed_category(file_path):
    base = get_base_category(file_path)
    ext = Path(file_path).suffix.lower()
    if base == "images":
        return "images/Photos" if is_photo_with_exif(file_path) else "images/Images"
    elif base == "documents":
        if ext == '.pdf': return "documents/PDF"
        elif ext in ('.doc', '.docx'): return "documents/Word"
        elif ext in ('.xls', '.xlsx', '.csv'): return "documents/Excel"
        else: return "documents/Text"
    elif base in ("videos", "audios", "archives"):
        return base
    else:
        return "other"


def get_dedup_key(file_path):
    stat = os.stat(file_path)
    size = stat.st_size
    mtime = stat.st_mtime
    if get_base_category(file_path) == "images":
        try:
            with Image.open(file_path) as img:
                exif = img._getexif() or {}
                exif_time = exif.get(36867) or exif.get(306)
                if exif_time:
                    dt = datetime.strptime(exif_time, "%Y:%m:%d %H:%M:%S")
                    return f"EXIF_{int(dt.timestamp())}_{size}"
        except Exception:
            pass
    return f"TIME_{int(mtime)}_{size}"


def get_unique_filename(dest_dir, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    dest_path = os.path.join(dest_dir, filename)
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_dir, f"{base} ({counter}){ext}")
        counter += 1
    return dest_path


def scan_all_files(source_dir):
    return [os.path.join(root, f) for root, _, files in os.walk(source_dir) for f in files]


# ==================== 主整理函数 v4.7（移动模式下重复文件也移动）===================
def organize_files(source_dir, target_root, mode="copy", progress_bar=None, status_label=None):
    if not source_dir or not target_root:
        messagebox.showerror("错误", "请先选择源目录和目标目录！")
        return

    is_move = (mode == "move")
    operation = shutil.move if is_move else shutil.copy2
    mode_name = "移动" if is_move else "拷贝"

    all_files = scan_all_files(source_dir)
    if not all_files:
        messagebox.showinfo("完成", "没有找到文件！")
        return

    seen = {}           # 用于判断是否重复
    duplicates = []
    success = 0
    total = len(all_files)

    duplicates_dir = os.path.join(target_root, "Duplicates")
    os.makedirs(duplicates_dir, exist_ok=True)
    log_path = os.path.join(target_root, "duplicates_log.txt")

    for i, src_path in enumerate(all_files):
        current_file = os.path.basename(src_path)
        year = get_year(src_path)
        category = get_detailed_category(src_path)

        progress_bar['value'] = (i + 1) / total * 100
        status_label.config(text=f"正在处理 ({i+1}/{total}): {current_file} [{mode_name}]")
        root.update_idletasks()

        if category == "other":
            final_dir = os.path.join(target_root, "other")
        else:
            final_dir = os.path.join(target_root, category, year)

        os.makedirs(final_dir, exist_ok=True)

        dedup_key = get_dedup_key(src_path)
        filename = current_file

        # ==================== 核心修正部分 ====================
        if dedup_key in seen:
            # 重复文件：无论拷贝还是移动，都移动到 Duplicates
            dest_path = get_unique_filename(duplicates_dir, filename)
            try:
                shutil.move(src_path, dest_path)          # 始终移动重复文件
                duplicates.append(f"重复文件: {src_path} → {dest_path}")
            except Exception as e:
                print(f"移动重复文件失败: {e}")
        else:
            # 非重复文件：按用户选择的模式操作
            dest_path = get_unique_filename(final_dir, filename)
            try:
                operation(src_path, dest_path)
                seen[dedup_key] = dest_path
                success += 1
            except Exception as e:
                print(f"{mode_name}失败: {filename} - {e}")

    # 写入日志
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== 文件分类整理日志 - {mode_name}模式 ===\n")
        f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"源目录: {source_dir}\n")
        f.write(f"总文件: {total}   成功处理: {success}   重复文件: {len(duplicates)}\n\n")
        if duplicates:
            f.write("=== 已移动到 Duplicates 的重复文件 ===\n")
            f.write("\n".join(duplicates))

    messagebox.showinfo("完成", f"整理完成！\n模式: {mode_name}\n总文件: {total}\n成功处理: {success}\n重复文件: {len(duplicates)}")


# ==================== GUI ====================
def main():
    global root
    root = tk.Tk()
    root.title("文件分类整理工具 v4.7")
    root.geometry("1000x720")

    tk.Label(root, text="文件分类整理工具 v4.7", font=("微软雅黑", 18, "bold")).pack(pady=15)
    tk.Label(root, text="拷贝 / 移动模式 | 自动按年份分类 | 重复文件统一移动到 Duplicates", fg="blue").pack(pady=5)

    frame = tk.Frame(root, padx=40, pady=15)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="1. 源目录：").grid(row=0, column=0, sticky="w", pady=6)
    source_var = tk.StringVar()
    tk.Entry(frame, textvariable=source_var, width=92).grid(row=1, column=0, sticky="ew", pady=4)
    tk.Button(frame, text="浏览", width=10, command=lambda: source_var.set(filedialog.askdirectory(title="选择源目录"))).grid(row=1, column=1, padx=8)

    tk.Label(frame, text="2. 目标根目录：").grid(row=2, column=0, sticky="w", pady=(12,6))
    target_var = tk.StringVar()
    tk.Entry(frame, textvariable=target_var, width=92).grid(row=3, column=0, sticky="ew", pady=4)
    tk.Button(frame, text="浏览", width=10, command=lambda: target_var.set(filedialog.askdirectory(title="选择目标目录"))).grid(row=3, column=1, padx=8)

    frame.columnconfigure(0, weight=1)

    mode_var = tk.StringVar(value="copy")
    mode_frame = tk.Frame(frame)
    mode_frame.grid(row=4, column=0, columnspan=2, pady=15)
    tk.Label(mode_frame, text="操作模式：", font=("", 10)).pack(side="left")
    tk.Radiobutton(mode_frame, text="拷贝（安全，默认）", variable=mode_var, value="copy").pack(side="left", padx=20)
    tk.Radiobutton(mode_frame, text="移动（彻底整理，源文件将被删除）", variable=mode_var, value="move", fg="#d32f2f").pack(side="left")

    progress = ttk.Progressbar(frame, orient="horizontal", length=800, mode="determinate")
    progress.grid(row=5, column=0, columnspan=2, pady=20, sticky="ew")

    status_label = tk.Label(frame, text="就绪 - 请先选择目录和操作模式", fg="#0066cc", font=("", 10))
    status_label.grid(row=6, column=0, columnspan=2, pady=8)

    def start():
        organize_files(source_var.get(), target_var.get(), mode_var.get(), progress, status_label)

    tk.Button(frame, text="🚀 开始整理文件", font=("微软雅黑", 13, "bold"),
              bg="#4CAF50", fg="white", height=2, command=start).grid(row=7, column=0, columnspan=2, pady=25, sticky="ew")

    root.mainloop()


if __name__ == "__main__":
    main()