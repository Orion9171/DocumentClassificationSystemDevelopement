import os
import shutil
import documents as doc
import re
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
SOURCE_DIR = "./new_data_folder"      # The directory to scan
DEST_DIR = "./working_folder"         # The directory to move files to


def folder_has_di_or_pdf(folder_path: str) -> bool:
    """
    檢查指定資料夾「本層」是否有 .di 或 .pdf。
    """
    try:
        for name in os.listdir(folder_path):
            lower_name = name.lower()
            if lower_name.endswith(".di") or lower_name.endswith(".pdf"):
                return True
    except Exception as e:
        print(f"Error checking folder '{folder_path}': {e}")

    return False


def import_selected_folder_to_new_data(selected_dir: str) -> int:
    """
    將使用者本地選到的資料夾複製到 ./new_data_folder。
    注意：這裡只 copy，不 move，所以本地原始資料不會消失。

    支援兩種情況：
    1. selected_dir 本身就是單一公文資料夾，裡面直接有 .di / .pdf
    2. selected_dir 是總資料夾，裡面有多個公文子資料夾
    """
    os.makedirs(SOURCE_DIR, exist_ok=True)

    imported_count = 0
    skipped_count = 0

    # Case 1：使用者選到的是單一公文資料夾，裡面直接有 .di / .pdf
    if folder_has_di_or_pdf(selected_dir):
        folder_name = os.path.basename(selected_dir.rstrip("/\\"))
        target_path = os.path.join(SOURCE_DIR, folder_name)

        if os.path.exists(target_path):
            skipped_count += 1
            print(f"Skip existing folder in new_data_folder: {folder_name}")
        else:
            shutil.copytree(selected_dir, target_path)
            imported_count += 1
            print(f"Copied selected folder to new_data_folder: {folder_name}")

        print(f"Import result: imported={imported_count}, skipped={skipped_count}")
        return imported_count

    # Case 2：使用者選到的是總資料夾，裡面有多個公文子資料夾
    for item in os.listdir(selected_dir):
        src_path = os.path.join(selected_dir, item)

        if not os.path.isdir(src_path):
            continue

        if not folder_has_di_or_pdf(src_path):
            continue

        target_path = os.path.join(SOURCE_DIR, item)

        if os.path.exists(target_path):
            skipped_count += 1
            print(f"Skip existing folder in new_data_folder: {item}")
            continue

        shutil.copytree(src_path, target_path)
        imported_count += 1
        print(f"Copied document folder to new_data_folder: {item}")

    print(f"Import result: imported={imported_count}, skipped={skipped_count}")
    return imported_count


def read_di_file(file_path: str) -> str:
    """
    讀取 .di 檔案內容。
    .di 通常是 XML，可能是 UTF-8 / Big5 / CP950。
    """
    encodings = ["utf-8", "utf-8-sig", "cp950", "big5"]

    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error reading DI file '{file_path}': {e}")
            return ""

    print(f"Error: Unable to decode DI file '{file_path}'.")
    return ""


def extract_instruction_from_di(file_path: str) -> str:
    """
    從 .di XML 檔中抽取：
    <主旨>
        <文字>...</文字>
    </主旨>
    """
    xml_text = read_di_file(file_path)

    if not xml_text:
        return ""

    # Remove XML DOCTYPE to avoid DTD / Entity parsing issues
    xml_text = re.sub(r"<!DOCTYPE[\s\S]*?\]>", "", xml_text).strip()

    try:
        root = ET.fromstring(xml_text)
        subject_node = root.find(".//主旨/文字")

        if subject_node is not None and subject_node.text:
            instruction = subject_node.text.strip()
            instruction = re.sub(r"\s+", "", instruction)
            return instruction

    except Exception as e:
        print(f"XML parsing error in DI file '{file_path}': {e}")

    # fallback: if XML parsing fails, use regex
    m = re.search(
        r"<主旨>\s*<文字>(.*?)</文字>\s*</主旨>",
        xml_text,
        flags=re.DOTALL
    )

    if m:
        instruction = m.group(1).strip()
        instruction = re.sub(r"\s+", "", instruction)
        return instruction

    print(f"Warning: No instruction found in DI file '{file_path}'.")
    return ""


def process_and_move_files(selected_dir=None):
    """
    正確 pipeline：

    如果 selected_dir 有值：
        本地 selected_dir
        -> copy 到 ./new_data_folder
        -> 再掃 ./new_data_folder

    不管 selected_dir 有沒有值，真正被 move / rmtree 的來源都只會是：
        ./new_data_folder

    因此本地原始資料夾不會被搬走。
    """
    # Step 0：如果 main.py 傳入本地資料夾，先 copy 到 ./new_data_folder
    if selected_dir:
        imported_count = import_selected_folder_to_new_data(selected_dir)
        if imported_count == 0:
            print("No new document folders imported. Stop processing.")
            return

    # Step 1：一律掃描 ./new_data_folder
    source_dir = SOURCE_DIR
    dest_dir = DEST_DIR

    # Ensure source directory exists
    if not os.path.exists(source_dir):
        os.makedirs(source_dir, exist_ok=True)
        print(f"Source directory '{source_dir}' did not exist. Created it.")
        return

    # Ensure destination directory exists
    os.makedirs(dest_dir, exist_ok=True)

    processed_count = 0

    # Loop through everything inside ./new_data_folder
    for item in os.listdir(source_dir):
        item_path = os.path.join(source_dir, item)

        # Check if the item is a subfolder
        if not os.path.isdir(item_path):
            continue

        di_file = None
        pdf_file = None

        # Scan inside the subfolder for .di and .pdf files
        for file in os.listdir(item_path):
            if file.lower().endswith(".di"):
                di_file = file
            elif file.lower().endswith(".pdf"):
                pdf_file = file

        if not di_file and not pdf_file:
            print(f"Skipping '{item}': No .di or .pdf files found inside.")
            continue

        # 1. Recreate the specific subfolder structure in the destination
        target_subfolder = os.path.join(dest_dir, item)
        os.makedirs(target_subfolder, exist_ok=True)

        # 2. Safely move the files from ./new_data_folder to ./working_folder
        if di_file:
            src_di = os.path.join(item_path, di_file)
            dst_di = os.path.join(target_subfolder, di_file)

            if os.path.exists(dst_di):
                os.remove(dst_di)

            shutil.move(src_di, dst_di)

        if pdf_file:
            src_pdf = os.path.join(item_path, pdf_file)
            dst_pdf = os.path.join(target_subfolder, pdf_file)

            if os.path.exists(dst_pdf):
                os.remove(dst_pdf)

            shutil.move(src_pdf, dst_pdf)

        # 3. Extract instruction from .di
        instruction = ""
        if di_file:
            instruction = extract_instruction_from_di(dst_di)
            print(f"Extracted instruction from {di_file}: {instruction}")

        # 4. Insert record into database
        doc.insert_document(
            di_filename=di_file or "",
            pdf_filename=pdf_file or "",
            folder_path=target_subfolder,
            instruction=instruction
        )

        # 5. Remove processed source folder inside ./new_data_folder
        try:
            shutil.rmtree(item_path)
            print(f"-> Successfully moved files, logged to DB, and REMOVED source folder: {item}")
        except Exception as e:
            print(f"-> Error removing folder {item}: {e}")

        print(f"-> Successfully moved files and inserted DB record for {item}.")
        processed_count += 1

    print(f"\nAll file processing and DB insertions are complete! Processed: {processed_count}")


if __name__ == "__main__":
    process_and_move_files()
