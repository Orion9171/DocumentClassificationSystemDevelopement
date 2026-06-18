import os
import shutil
import sqlite3
import documents as doc

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

                # read the .di file and extract the instruction here, then pass it to the insert_document function
                instruction = ''
                #
                    
                if pdf_file:
                    src_pdf = os.path.join(item_path, pdf_file)
                    dst_pdf = os.path.join(target_subfolder, pdf_file)
                    shutil.move(src_pdf, dst_pdf)
                
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