import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime
import hashlib
import time

# ==================== 辅助函数 ====================
def get_year(file_path):
    try:
        return str(datetime.fromtimestamp(os.path.getmtime(file_path)).year)
    except Exception:
        return "未知年份"


def get_base_category(file_path, other_extensions):
    ext = Path(file_path).suffix.lower()
    if ext in {'.doc', '.docx', '.pdf', '.txt'}:
        return "text"
    if ext in other_extensions or ext in {'.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar'}:
        return "other"
    return "ignore"  # 其他文件暂时忽略（可后续扩展）


def get_dedup_key(file_path):
    """用于初步筛选"""
    stat = os.stat(file_path)
    size = stat.st_size
    mtime = int(stat.st_mtime)
    return f"{mtime}_{size}"


def compute_sha256(file_path):
    """计算 SHA-256"""
    try:
        hash_sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_sha.update(chunk)
        return hash_sha.hexdigest()
    except Exception:
        return None


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


# ==================== 主整理函数 ====================
def organize_files(source_dir, target_root, mode="copy", other_exts=None, progress_bar=None, status_label=None, root=None):
    if not source_dir or not target_root:
        messagebox.showerror("错误", "请先选择源目录和目标目录！")
        return

    start_time = time.time()
    is_move = (mode == "move")
    operation = shutil.move if is_move else shutil.copy2
    mode_name = "移动" if is_move else "拷贝"

    other_extensions = {ext.strip().lower() for ext in (other_exts or "") if ext.strip()}

    all_files = scan_all_files(source_dir)
    if not all_files:
        messagebox.showinfo("完成", "没有找到文件！")
        return

    seen = {}           # key: sha256 → 保留的文件路径
    duplicates = []
    stats = {"text": 0, "other": 0}
    suffix_count = {}
    total = len(all_files)
    success = 0

    duplicate_dir = os.path.join(target_root, "duplicate")
    os.makedirs(duplicate_dir, exist_ok=True)

    for i, src_path in enumerate(all_files):
        current_file = os.path.basename(src_path)
        ext = Path(src_path).suffix.lower()
        suffix_count[ext] = suffix_count.get(ext, 0) + 1

        if progress_bar is not None:
            progress_bar['value'] = (i + 1) / total * 100
        if status_label is not None:
            status_label.config(text=f"正在处理 ({i+1}/{total}): {current_file}")
        if root is not None:
            root.update_idletasks()

        category = get_base_category(src_path, other_extensions)
        if category == "ignore":
            continue

        year = get_year(src_path)
        folder_name = "文本文件" if category == "text" else "其他文件"
        final_dir = os.path.join(target_root, f"{year}年", folder_name)
        os.makedirs(final_dir, exist_ok=True)

        # ==================== 重复检测 ====================
        is_duplicate = False
        if ext in {'.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx'}:
            dedup_key = get_dedup_key(src_path)
            sha256 = compute_sha256(src_path)

            if sha256:
                if sha256 in seen:
                    is_duplicate = True
                else:
                    # 大小相近 + 时间相同 才认为是潜在重复（额外保护）
                    for existing_sha, existing_path in list(seen.items()):
                        if abs(os.path.getsize(src_path) - os.path.getsize(existing_path)) <= 10:
                            if dedup_key.split('_')[0] == get_dedup_key(existing_path).split('_')[0]:
                                if compute_sha256(existing_path) == sha256:  # 二次确认
                                    is_duplicate = True
                                    break

        if is_duplicate:
            dest_path = get_unique_filename(duplicate_dir, current_file)
            try:
                shutil.move(src_path, dest_path)
                duplicates.append(f"{src_path} → {dest_path}")
            except Exception as e:
                print(f"移动重复文件失败: {e}")
        else:
            dest_path = get_unique_filename(final_dir, current_file)
            try:
                operation(src_path, dest_path)
                if sha256:  # 记录非重复文件的哈希
                    seen[sha256] = dest_path
                success += 1
                stats[category] += 1
            except Exception as e:
                print(f"{mode_name}失败: {e}")

    # ==================== 写入日志 ====================
    end_time = time.time()
    runtime = f"{end_time - start_time:.2f} 秒"

    log_path = os.path.join(target_root, "file_organizer_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=== 文件分类整理日志 ===\n")
        f.write(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"程序耗时: {runtime}\n\n")
        f.write(f"源目录: {source_dir}\n")
        f.write(f"目标根目录: {target_root}\n")
        f.write(f"操作模式: {mode_name}\n\n")
        f.write(f"文本文件（.doc/.docx/.pdf/.txt）: {stats['text']} 个\n")
        f.write(f"其他文件（.xls/.ppt/.zip等）: {stats['other']} 个\n")
        f.write(f"重复文件: {len(duplicates)} 个\n")
        f.write(f"总处理文件: {total} 个\n\n")

        f.write("=== 各后缀统计 ===\n")
        for ext, cnt in sorted(suffix_count.items()):
            f.write(f"{ext}: {cnt} 个\n")

        if duplicates:
            f.write("\n=== 重复文件列表 ===\n")
            f.write("\n".join(duplicates))

    messagebox.showinfo("完成", f"整理完成！\n"
                                f"模式: {mode_name}\n"
                                f"文本文件: {stats['text']}\n"
                                f"其他文件: {stats['other']}\n"
                                f"重复文件: {len(duplicates)}\n"
                                f"耗时: {runtime}")


# ==================== GUI ====================
def main():
    global root
    root = tk.Tk()
    root.title("文件分类整理工具 v5.0")
    root.geometry("1050x750")

    tk.Label(root, text="文件分类整理工具 v5.0", font=("微软雅黑", 18, "bold")).pack(pady=15)
    tk.Label(root, text="文档自动分类 | 智能去重（SHA-256） | 增强日志", fg="blue").pack(pady=5)

    frame = tk.Frame(root, padx=40, pady=15)
    frame.pack(fill="both", expand=True)

    # 源目录
    tk.Label(frame, text="1. 源目录：").grid(row=0, column=0, sticky="w", pady=6)
    source_var = tk.StringVar()
    tk.Entry(frame, textvariable=source_var, width=95).grid(row=1, column=0, sticky="ew", pady=4)
    tk.Button(frame, text="浏览", width=10, command=lambda: source_var.set(filedialog.askdirectory(title="选择源目录"))).grid(row=1, column=1, padx=8)

    # 目标目录
    tk.Label(frame, text="2. 目标根目录：").grid(row=2, column=0, sticky="w", pady=(12,6))
    target_var = tk.StringVar()
    tk.Entry(frame, textvariable=target_var, width=95).grid(row=3, column=0, sticky="ew", pady=4)
    tk.Button(frame, text="浏览", width=10, command=lambda: target_var.set(filedialog.askdirectory(title="选择目标目录"))).grid(row=3, column=1, padx=8)

    frame.columnconfigure(0, weight=1)

    # 操作模式
    mode_var = tk.StringVar(value="copy")
    mode_frame = tk.Frame(frame)
    mode_frame.grid(row=4, column=0, columnspan=2, pady=12)
    tk.Label(mode_frame, text="操作模式：").pack(side="left")
    tk.Radiobutton(mode_frame, text="拷贝（安全）", variable=mode_var, value="copy").pack(side="left", padx=20)
    tk.Radiobutton(mode_frame, text="移动（彻底整理）", variable=mode_var, value="move", fg="#d32f2f").pack(side="left")

    # 其他文件额外后缀
    tk.Label(frame, text="3. 其他文件额外后缀（用逗号分隔）:").grid(row=5, column=0, sticky="w", pady=(15,5))
    extra_ext_var = tk.StringVar(value=".ppt,.pptx")
    tk.Entry(frame, textvariable=extra_ext_var, width=95).grid(row=6, column=0, sticky="ew", pady=4)

    progress = ttk.Progressbar(frame, orient="horizontal", length=850, mode="determinate")
    progress.grid(row=7, column=0, columnspan=2, pady=20, sticky="ew")

    status_label = tk.Label(frame, text="就绪 - 请设置目录和模式", fg="#0066cc", font=("", 10))
    status_label.grid(row=8, column=0, columnspan=2, pady=8)

    def start():
        organize_files(
            source_var.get(),
            target_var.get(),
            mode_var.get(),
            extra_ext_var.get(),
            progress,
            status_label,
            root
        )

    tk.Button(frame, text="🚀 开始整理文件", font=("微软雅黑", 13, "bold"),
              bg="#4CAF50", fg="white", height=2, command=start).grid(row=9, column=0, columnspan=2, pady=25, sticky="ew")

    root.mainloop()


if __name__ == "__main__":
    main()