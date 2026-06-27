import os
import shutil
import sqlite3
import documents as doc
import re
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
SOURCE_DIR = "./new_data_folder"      # The directory to scan
DEST_DIR = "./working_folder"    # The directory to move files to


def process_and_move_files():
    # Ensure source directory exists
    if not os.path.exists(SOURCE_DIR):
        print(f"Error: Source directory '{SOURCE_DIR}' does not exist.")
        return
    # Ensure destination directory exists (create if it doesn't)
    os.makedirs(DEST_DIR, exist_ok=True)

    # Loop through everything inside the main working folder
    for item in os.listdir(SOURCE_DIR):
        item_path = os.path.join(SOURCE_DIR, item)
        
        # Check if the item is a subfolder (e.g., folder1, folder2)
        if os.path.isdir(item_path):
            di_file = None
            pdf_file = None
            
            # Scan inside the subfolder for .di and .pdf files
            for file in os.listdir(item_path):
                if file.lower().endswith('.di'):
                    di_file = file
                elif file.lower().endswith('.pdf'):
                    pdf_file = file

            # If we found at least one of the target files, handle migration & DB entry
            if di_file or pdf_file:
                # print(f"Processing '{item}': Found DI='{di_file}', PDF='{pdf_file}'")
                
                # 1. Recreate the specific subfolder structure in the destination
                target_subfolder = os.path.join(DEST_DIR, item)
                os.makedirs(target_subfolder, exist_ok=True)
                
                # 2. Safely move the files if they exist
                if di_file:
                    src_di = os.path.join(item_path, di_file)
                    dst_di = os.path.join(target_subfolder, di_file)
                    shutil.move(src_di, dst_di)
                if pdf_file:
                    src_pdf = os.path.join(item_path, pdf_file)
                    dst_pdf = os.path.join(target_subfolder, pdf_file)
                    shutil.move(src_pdf, dst_pdf)

                # read the .di file and extract the instruction here, then pass it to the insert_document function
                def read_di_file(file_path: str) -> str:
                    """
                    reads the content of a .di file with multiple encoding attempts and returns the content as a string. 
                    If all attempts fail, it returns an empty string.
                    """
                    encodings = ["utf-8", "utf-8-sig", "cp950", "big5"]
                    for enc in encodings:
                        try:
                            with open(file_path,"r", encoding = enc) as f:
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
                    from. di XML file, extract the instruction text like
                    <主旨>
                        <文字>...</文字>
                    </主旨>
                    """
                    xml_text = read_di_file(file_path)
                    if not xml_text:
                        return ""   
                    #remove XML DOCTYPE to avoid DTD/Entity parsing issues
                    xml_text =  re.sub(r"<!DOCTYPE[\s\S]*?\]>", "", xml_text).strip()
                    
                    try:
                        root = ET.fromstring(xml_text)
                        subject_node = root.find('.//主旨/文字')
                        if subject_node is not None and subject_node.text:
                           instruction = subject_node.text.strip()
                           instruction = re.sub(r"\s+", "", instruction)
                           return instruction
                    except Exception as e:
                        print(f"XML parsing error in DI file '{file_path}': {e}")
                    # fallback: if XML parsing fails, we use regex to extract the instruction
                    m = re.search(r"<主旨>\s*<文字>(.*?)</文字>\s*</主旨>", xml_text, re.DOTALL)
                    if m:
                        instruction = m.group(1).strip()     
                        instruction = re.sub(r"\s+", "", instruction)
                        return instruction
                    print(f"Warning: No instruction found in DI file '{file_path}'.")
                    return "" 
                
                 # from .di XML extract <主旨><文字>...</文字></主旨>
                instruction = ''
                if di_file:
                    instruction = extract_instruction_from_di(dst_di)
                    print(f"Extracted instruction from {di_file}: {instruction}")
                
                # 3. Insert records into the database
                doc.insert_document(di_filename=di_file or '', 
                                    pdf_filename=pdf_file or '', 
                                    folder_path=target_subfolder, 
                                    instruction=instruction)  #put the document instruction here
                
                # 4. REMOVE THE OLD FOLDER
                # rmtree deletes the folder even if "other files" are still inside it
                try:
                    shutil.rmtree(item_path)
                    print(f"-> Successfully moved files, logged to DB, and REMOVED source folder: {item}")
                except Exception as e:
                    print(f"-> Error removing folder {item}: {e}")
                    
                print(f"-> Successfully moved files and inserted DB record for {item}.")
            else:
                print(f"Skipping '{item}': No .di or .pdf files found inside.")

    print("\nAll file processing and DB insertions are complete!")


if __name__ == "__main__":
    process_and_move_files()