import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os

def process_html(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex for capturing <script> tags
        script_pattern = re.compile(r'<script\b[^>]*>.*?</script>', re.DOTALL | re.IGNORECASE)
        
        count_removed_1 = 0
        count_removed_2 = 0
        
        def replacer(match):
            nonlocal count_removed_1, count_removed_2
            text = match.group(0)
            
            # 1. Check for insertYourRemoteDebugging
            if 'insertYourRemoteDebugging' in text:
                count_removed_1 += 1
                return ''
                
            # 2. Check for data-startup-only AND absolute URL (http/https)
            if 'data-startup-only' in text and re.search(r'https?://', text, re.IGNORECASE):
                count_removed_2 += 1
                return ''
                
            return text

        content = script_pattern.sub(replacer, content)
        
        # Validation for finding at least one of each, or just checking if both were not found.
        # "nếu không xóa được 2 script ở mục 1 và 2 thì sẽ thông báo có lỗi xảy ra"
        # We will require both to be > 0.
        if count_removed_1 == 0 or count_removed_2 == 0:
            return False, "Lỗi: Không tìm thấy hoặc không thể xóa đủ 2 loại script yêu cầu (insertYourRemoteDebugging và data-startup-only kèm link cứng)."

        # 3. Replace other html links
        # "Nếu còn chỗ nào khác ngoài 2 tag script trên chứa link html dạng như này "link" thì sẽ xóa đường link đó đi chỉ còn lại dấu nháy như này """
        # We remove exact literal "link" just in case:
        content = re.sub(r'"link"', '""', content)
        content = re.sub(r"'link'", "''", content)
        
        # We also remove absolute urls in quotes:
        content = re.sub(r'"https?://[^"]+"', '""', content, flags=re.IGNORECASE)
        content = re.sub(r"'https?://[^']+'", "''", content, flags=re.IGNORECASE)
        
        # Replace href="..." and src="..." if they look like links just to be safe
        content = re.sub(r'(href\s*=\s*)"[^"]+"', r'\1""', content, flags=re.IGNORECASE)
        content = re.sub(r"(href\s*=\s*)'[^']+'", r"\1''", content, flags=re.IGNORECASE)

        # Save file ending with _AL
        base, ext = os.path.splitext(file_path)
        new_file_path = base + "_AL" + ext
        
        with open(new_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return True, "Convert thành công sang AL"
        
    except Exception as e:
        return False, f"Có lỗi xảy ra: {str(e)}"

def main():
    root = tk.Tk()
    root.withdraw() # Hide the main window
    
    # Show file dialog
    file_path = filedialog.askopenfilename(
        title="Chọn file HTML để convert",
        filetypes=[("HTML files", "*.html *.htm")]
    )
    
    if not file_path:
        return
        
    success, msg = process_html(file_path)
    
    if success:
        messagebox.showinfo("Thành công", msg)
    else:
        messagebox.showerror("Lỗi", msg)

if __name__ == "__main__":
    main()
