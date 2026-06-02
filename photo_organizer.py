import os
import shutil
import tkinter as tk
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

# 可扩展：视频
MOV_EXTENSIONS = {
    ".mov",
    ".mp4",
    ".m4v",
    ".avi",
    ".mkv",
    ".wmv",
    ".webm",
    ".mpg",
    ".mpeg",
    ".3gp",
}

# 可扩展：原始底片
RAW_EXTENSIONS = {
    ".cr2",
    ".nef",
    ".dng",
    ".arw",
    ".orf",
    ".rw2",
    ".raf",
}

JPEG_EXTENSIONS = {".jpg", ".jpeg"}

# 勿使用单独的 "screen"，否则会误匹配 myscreen、widescreen、*.ds_store 等，误入 IMG
IMG_KEYWORDS = (
    "screenshot",
    "screen shot",
    "screen-shot",
    "screen_shot",
    "截屏",
    "截图",
    "捕获",
)

EXIF_TIME_TAGS = (36867, 36868, 306)


def clear_windows_hidden_system_attr(path):
    """
    去掉目标文件的「隐藏/系统」属性。Windows 下 copy2/move 会继承源属性，
    无扩展名等文件在源盘上常为隐藏，复制后在资源管理器默认视图中会像「空文件夹」。
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        abspath = os.path.abspath(path)
        FILE_ATTRIBUTE_NORMAL = 0x80
        ctypes.windll.kernel32.SetFileAttributesW(abspath, FILE_ATTRIBUTE_NORMAL)
    except Exception:
        pass


def clear_hidden_attrs_under(root_dir):
    """递归清除目录下全部文件的隐藏/系统属性；返回处理的文件数。"""
    n = 0
    if os.name != "nt" or not os.path.isdir(root_dir):
        return n
    for walk_root, _, fnames in os.walk(root_dir):
        for fname in fnames:
            clear_windows_hidden_system_attr(os.path.join(walk_root, fname))
            n += 1
    return n


def parse_exif_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def get_exif_datetime(file_path):
    try:
        with Image.open(file_path) as img:
            exif = img.getexif() or {}
            for tag in EXIF_TIME_TAGS:
                dt = parse_exif_datetime(exif.get(tag))
                if dt:
                    return dt
    except Exception:
        return None
    return None


def get_year_for_dest(category, exif_dt, file_path):
    if category == "PHOTO" and exif_dt:
        return exif_dt.year
    if category == "HEIC":
        if exif_dt:
            return exif_dt.year
        return datetime.fromtimestamp(os.path.getmtime(file_path)).year
    return datetime.fromtimestamp(os.path.getmtime(file_path)).year


def matches_img_keywords(file_path):
    base = os.path.basename(file_path).lower()
    return any(k in base for k in IMG_KEYWORDS)


def classify_file(file_path):
    """
    返回 (大类文件夹名, exif_dt 或 None)。
    优先级：MOV > RAW > IMG（含 png/bmp/关键词）> JPEG 分支 > HEIC > other
    无后缀文件一律为 other；other 类输出到 output\\other\\（不按年份）。
    """
    ext = Path(file_path).suffix.lower()
    if not ext:
        return "other", None

    if ext in MOV_EXTENSIONS:
        return "MOV", None
    if ext in RAW_EXTENSIONS:
        return "RAW", None
    # Finder / 拷贝残留索引文件，避免被 IMG 关键词误伤
    if ext == ".ds_store":
        return "other", None
    if ext in (".png", ".bmp") or matches_img_keywords(file_path):
        return "IMG", None
    if ext in JPEG_EXTENSIONS:
        exif_dt = get_exif_datetime(file_path)
        if exif_dt:
            return "PHOTO", exif_dt
        return "JPEG", None
    if ext == ".heic":
        return "HEIC", get_exif_datetime(file_path)
    return "other", None


def other_destination_dir(output_root):
    """
    other 类归档目录。若用户把输出目录直接选成「…\\other」，
    则不再套一层 other\\other，文件直接进该目录。
    """
    norm = os.path.normpath(output_root)
    if os.path.basename(norm).lower() == "other":
        return norm
    return os.path.join(norm, "other")


def unique_destination(dest_dir, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base} ({index}){ext}")
        index += 1
    return candidate


def scan_input_files(source_dir):
    """递归遍历 input，返回全部文件路径与按后缀统计。"""
    all_paths = []
    for root, _, files in os.walk(source_dir):
        for name in files:
            all_paths.append(os.path.join(root, name))

    ext_counts = Counter()
    for p in all_paths:
        suf = Path(p).suffix.lower()
        ext_counts[suf if suf else "(无扩展名)"] += 1

    return all_paths, ext_counts


def write_filecount(output_root, source_dir, total, ext_counts):
    os.makedirs(output_root, exist_ok=True)
    path = os.path.join(output_root, "filecount.txt")
    lines = [
        f"生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"输入目录: {source_dir}",
        f"文件总数: {total}",
        "",
        "各后缀文件数（后缀小写；无扩展名记为 (无扩展名)）:",
    ]
    for ext in sorted(ext_counts.keys(), key=lambda x: (x == "(无扩展名)", x)):
        lines.append(f"  {ext}: {ext_counts[ext]}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def organize_photos(source_dir, output_root, mode, progress_bar, status_label):
    if not source_dir or not output_root:
        messagebox.showerror("错误", "请先选择输入目录（input）和输出目录（output）。")
        return

    if not os.path.isdir(source_dir):
        messagebox.showerror("错误", f"输入目录不存在：\n{source_dir}")
        return

    os.makedirs(output_root, exist_ok=True)
    progress_bar["value"] = 0
    status_label.config(text="正在扫描输入目录…")

    all_files, ext_counts = scan_input_files(source_dir)
    total = len(all_files)
    filecount_path = write_filecount(output_root, source_dir, total, ext_counts)

    if not all_files:
        messagebox.showinfo("完成", f"输入目录下没有文件。\n\n已写入：\n{filecount_path}")
        return

    operation = shutil.move if mode == "move" else shutil.copy2
    mode_name = "移动" if mode == "move" else "拷贝"
    success = 0
    failed = []
    category_counts = Counter()
    other_root = other_destination_dir(output_root)

    for index, src_path in enumerate(all_files, start=1):
        filename = os.path.basename(src_path)
        category, exif_dt = classify_file(src_path)
        if category == "other":
            dest_dir = other_root
            dest_hint = "other"
        else:
            year = get_year_for_dest(category, exif_dt, src_path)
            year_str = f"{year:04d}"
            dest_dir = os.path.join(output_root, year_str)
            dest_hint = year_str
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = unique_destination(dest_dir, filename)

        try:
            operation(src_path, dest_path)
            success += 1
            category_counts[category] += 1
        except Exception as exc:
            failed.append((src_path, str(exc)))

        progress_bar["value"] = index / total * 100
        status_label.config(
            text=f"正在处理 ({index}/{total})：{filename} → {dest_hint} [{mode_name}]"
        )
        root.update_idletasks()

    # 一次性格式化输出目录下所有文件的属性（copy2 会继承源的隐藏/系统位）
    cleared_n = clear_hidden_attrs_under(output_root)

    log_path = os.path.join(output_root, "photo_organize_log.txt")
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        log_file.write(f"模式: {mode_name}\n")
        log_file.write(f"输入目录: {source_dir}\n")
        log_file.write(f"输出目录: {output_root}\n")
        log_file.write(f"other 类实际路径: {other_root}\n")
        log_file.write(f"总文件: {total}\n")
        log_file.write(f"成功: {success}\n")
        log_file.write(f"失败: {len(failed)}\n")
        log_file.write(f"统计文件: {filecount_path}\n")
        if os.name == "nt":
            log_file.write(f"已清除隐藏/系统属性的文件数（整棵输出目录）: {cleared_n}\n")
        log_file.write("\n各分类归档数量（按判定结果）:\n")
        for cat in sorted(category_counts.keys()):
            log_file.write(f"  {cat}: {category_counts[cat]}\n")
        log_file.write("\n")
        if os.path.isdir(other_root):
            try:
                other_n = len([x for x in os.listdir(other_root) if os.path.isfile(os.path.join(other_root, x))])
                log_file.write(f"other 目录内文件数（仅统计该文件夹下一层）: {other_n}\n")
                log_file.write(
                    "提示: 若资源管理器中看起来像空文件夹，请在「查看」中勾选「隐藏的项目」，\n"
                    "或右键 other → 属性，确认本程序已清除隐藏属性（见上文处理逻辑）。\n\n"
                )
            except OSError:
                pass
        if failed:
            log_file.write("失败明细:\n")
            for src, err in failed:
                log_file.write(f"- {src}\n  错误: {err}\n")

    messagebox.showinfo(
        "完成",
        (
            f"整理完成！\n模式: {mode_name}\n总文件: {total}\n"
            f"成功: {success}\n失败: {len(failed)}\n\n"
            f"统计: {filecount_path}\n"
            f"日志: {log_path}"
        ),
    )


def _pick_dir(var, title, must_exist=True):
    """打开系统文件夹对话框；首次从用户主目录起选。"""
    initial = var.get().strip()
    if not initial or not os.path.isdir(initial):
        initial = os.path.expanduser("~")
    try:
        path = filedialog.askdirectory(
            title=title,
            initialdir=initial,
            mustexist=must_exist,
        )
    except TypeError:
        path = filedialog.askdirectory(title=title, initialdir=initial)
    if path:
        var.set(path)


def main():
    global root
    root = tk.Tk()
    root.title("照片归档工具（按年）— 浏览选择目录")
    # 默认高度需大于内容总高度，否则底部「开始整理」会被窗口裁切（尤其高分屏）
    root.geometry("780x620")
    root.minsize(680, 540)

    header = tk.Frame(root)
    header.pack(fill="x", padx=28, pady=(32, 0))
    tk.Label(header, text="照片归档工具", font=("微软雅黑", 17, "bold")).pack(
        pady=(0, 8), anchor="center"
    )
    tk.Label(
        header,
        text="输入为多层目录；除 other 外输出为 output\\YYYY\\ ；other 类为 output\\other\\（不按年份）",
        fg="blue",
    ).pack(pady=(0, 6))
    tk.Label(
        header,
        text="请使用下方「浏览…」打开系统文件夹对话框，选择要处理的目录与输出目录（无需手输路径）。",
        fg="#555555",
    ).pack(pady=(0, 14))

    frame = tk.Frame(root, padx=28, pady=8)
    # 底部留白：避免最后一行控件贴边被裁切
    frame.pack(fill="x", expand=False, pady=(0, 16))
    frame.columnconfigure(0, weight=1)

    dir_frame = tk.LabelFrame(frame, text=" 选择目录（浏览） ", padx=10, pady=10)
    dir_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
    dir_frame.columnconfigure(0, weight=1)

    tk.Label(dir_frame, text="1. 输入目录（待整理的多层文件夹）").grid(row=0, column=0, sticky="w", pady=(0, 4))
    source_var = tk.StringVar(value=r"D:\input")
    path_row = tk.Frame(dir_frame)
    path_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
    path_row.columnconfigure(0, weight=1)
    tk.Entry(path_row, textvariable=source_var, width=68).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    tk.Button(
        path_row,
        text="浏览…",
        width=10,
        command=lambda: _pick_dir(source_var, "选择输入目录（input）", must_exist=True),
    ).grid(row=0, column=1)

    tk.Label(dir_frame, text="2. 输出目录（将生成 filecount.txt、各年份子目录与 other 目录）").grid(
        row=2, column=0, sticky="w", pady=(12, 4)
    )
    target_var = tk.StringVar(value=r"D:\output")
    path_row2 = tk.Frame(dir_frame)
    path_row2.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
    path_row2.columnconfigure(0, weight=1)
    tk.Entry(path_row2, textvariable=target_var, width=68).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    tk.Button(
        path_row2,
        text="浏览…",
        width=10,
        command=lambda: _pick_dir(target_var, "选择输出目录（output）", must_exist=False),
    ).grid(row=0, column=1)

    mode_var = tk.StringVar(value="copy")
    mode_frame = tk.Frame(frame)
    mode_frame.grid(row=4, column=0, columnspan=2, pady=(10, 8))
    tk.Label(mode_frame, text="操作模式：").pack(side="left")
    tk.Radiobutton(mode_frame, text="拷贝（推荐）", variable=mode_var, value="copy").pack(side="left", padx=20)
    tk.Radiobutton(
        mode_frame,
        text="移动（源文件会被移走）",
        variable=mode_var,
        value="move",
        fg="#d32f2f",
    ).pack(side="left")

    progress = ttk.Progressbar(frame, orient="horizontal", length=660, mode="determinate")
    progress.grid(row=5, column=0, columnspan=2, pady=(8, 10), sticky="ew")

    status_label = tk.Label(frame, text="就绪 - 请选择输入目录、输出目录与模式", fg="#0066cc")
    status_label.grid(row=6, column=0, columnspan=2, pady=(16, 4))

    def start():
        organize_photos(
            source_var.get().strip(),
            target_var.get().strip(),
            mode_var.get(),
            progress,
            status_label,
        )

    tk.Button(
        frame,
        text="开始整理",
        font=("微软雅黑", 12, "bold"),
        bg="#4CAF50",
        fg="white",
        height=2,
        command=start,
    ).grid(row=7, column=0, columnspan=2, pady=(8, 0), sticky="ew")

    # 按实际内容高度设置窗口，避免固定高度过小导致底部按钮被裁切
    root.update_idletasks()
    req_w = root.winfo_reqwidth()
    req_h = root.winfo_reqheight()
    if req_w > 1 and req_h > 1:
        root.geometry(f"{max(780, req_w)}x{req_h + 32}")

    root.mainloop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--clear-hidden":
        target = sys.argv[2].strip()
        if not os.path.isdir(target):
            print(f"目录不存在: {target}", file=sys.stderr)
            sys.exit(1)
        count = clear_hidden_attrs_under(target)
        print(f"已清除隐藏/系统属性: {count} 个文件\n{os.path.abspath(target)}")
        sys.exit(0)

    main()
