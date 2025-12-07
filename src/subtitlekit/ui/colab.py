"""
Google Colab UI using ipywidgets - Enhanced version

This module provides a Jupyter/Colab-friendly interface for subtitle processing
with file pickers, JSON paste, and better dark mode support.
"""
import ipywidgets as widgets
from IPython.display import display, HTML
from google.colab import files
import json
import os
import glob


def show_ui(lang='en'):
    """
    Display subtitle processing UI in Jupyter/Colab notebook.
    
    Args:
        lang: Language for UI ('en' or 'el')
    """
    # Import functions
    try:
        from subtitlekit.tools.matcher import process_subtitles
        from subtitlekit.tools.overlaps import fix_problematic_timings
        from subtitlekit.tools.corrections import apply_corrections_from_file
    except ImportError:
        print("⚠️ Could not import subtitlekit. Make sure it's installed: pip install subtitlekit")
        return
    
    # Translations
    translations = {
        'en': {
            'title': '📝 SubtitleKit - Subtitle Processing',
            'tab_merge': 'Merge Subtitles',
            'tab_overlaps': 'Fix Overlaps',
            'tab_corrections': 'Apply Corrections',
            'label_original': 'Original subtitle:',
            'label_helper': 'Helper subtitles (comma-separated):',
            'label_input': 'Input subtitle:',
            'label_reference': 'Reference subtitle:',
            'label_corrections_file': 'Corrections file:',
            'label_corrections_json': 'Or paste JSON:',
            'label_output': 'Output filename:',
            'label_postfix': 'Output postfix:',
            'label_window': 'Window size:',
            'button_upload': 'Upload File',
            'button_process': 'Process',
            'checkbox_skip_sync': 'Skip synchronization',
            'checkbox_preprocess': 'Preprocess input',
            'checkbox_auto_download': 'Auto-download result',
            'status_upload': 'Click Upload to select file',
            'status_processing': '⏳ Processing...',
            'status_success': '✅ Success!',
            'status_error': '❌ Error: ',
            'msg_no_files': 'Please select or upload files first',
            'msg_json_error': '❌ JSON parse error: ',
        },
        'el': {
            'title': '📝 SubtitleKit - Επεξεργασία Υποτίτλων',
            'tab_merge': 'Ένωση Υποτίτλων',
            'tab_overlaps': 'Διόρθωση Χρονισμών',
            'tab_corrections': 'Εφαρμογή Διορθώσεων',
            'label_original': 'Αρχικός υπότιτλος:',
            'label_helper': 'Βοηθητικοί υπότιτλοι (με κόμμα):',
            'label_input': 'Υπότιτλος εισόδου:',
            'label_reference': 'Υπότιτλος αναφοράς:',
            'label_corrections_file': 'Αρχείο διορθώσεων:',
            'label_corrections_json': 'Ή επικόλληση JSON:',
            'label_output': 'Όνομα αρχείου εξόδου:',
            'label_postfix': 'Κατάληξη εξόδου:',
            'label_window': 'Μέγεθος παραθύρου:',
            'button_upload': 'Ανέβασμα Αρχείου',
            'button_process': 'Επεξεργασία',
            'checkbox_skip_sync': 'Παράλειψη συγχρονισμού',
            'checkbox_preprocess': 'Προεπεξεργασία',
            'checkbox_auto_download': 'Αυτόματο κατέβασμα',
            'status_upload': 'Κλικ για ανέβασμα',
            'status_processing': '⏳ Επεξεργασία...',
            'status_success': '✅ Επιτυχία!',
            'status_error': '❌ Σφάλμα: ',
            'msg_no_files': 'Παρακαλώ επιλέξτε ή ανεβάστε αρχεία',
            'msg_json_error': '❌ Σφάλμα JSON: ',
        }
    }
    
    t = translations.get(lang, translations['en'])
    
    # Custom CSS for better dark mode support
    display(HTML("""
    <style>
    .widget-label { color: var(--colab-primary-text-color, #202124) !important; }
    .widget-text input, .widget-dropdown select, .widget-textarea textarea {
        background-color: var(--colab-secondary-surface-color, #fff) !important;
        color: var(--colab-primary-text-color, #202124) !important;
        border: 1px solid var(--colab-border-color, #dadce0) !important;
    }
    .widget-button { 
        background-color: #1a73e8 !important;
        color: white !important;
        border: none !important;
    }
    .output_area { 
        background-color: var(--colab-secondary-surface-color, #f8f9fa) !important;
        color: var(--colab-primary-text-color, #202124) !important;
        padding: 10px !important;
        border-radius: 4px !important;
    }
    </style>
    """))
    
    # Display title
    display(HTML(f"<h2 style='color: var(--colab-primary-text-color, #202124);'>{t['title']}</h2>"))
    
    # Shared list of all dropdowns for refreshing
    all_srt_dropdowns = []
    all_json_dropdowns = []
    
    def refresh_all_dropdowns():
        """Refresh file options in all dropdowns"""
        srt_files = [''] + sorted(glob.glob('*.srt'))
        json_files = [''] + sorted(glob.glob('*.json'))
        
        for dropdown in all_srt_dropdowns:
            current = dropdown.value
            dropdown.options = srt_files
            if current in srt_files:
                dropdown.value = current
        
        for dropdown in all_json_dropdowns:
            current = dropdown.value
            dropdown.options = json_files
            if current in json_files:
                dropdown.value = current
    
    def generate_output_filename(input_filename, postfix, extension):
        """Generate output filename from input with postfix"""
        if not input_filename:
            return ''
        basename = os.path.splitext(input_filename)[0]
        return f"{basename}{postfix}.{extension}"
    
    # Helper: File picker widget
    def create_file_picker(label, file_types='*.srt', output_widget=None, postfix_widget=None, extension='srt'):
        """Create a file picker with upload option"""
        is_json = file_types == '*.json'
        options = [''] + sorted(glob.glob(file_types))
        
        dropdown = widgets.Dropdown(
            options=options,
            description=label,
            style={'description_width': '150px'},
            layout=widgets.Layout(width='500px')
        )
        
        # Track dropdown based on type
        if is_json:
            all_json_dropdowns.append(dropdown)
        else:
            all_srt_dropdowns.append(dropdown)
        
        upload_btn = widgets.Button(description=t['button_upload'], button_style='info', layout=widgets.Layout(width='120px'))
        upload_status = widgets.HTML(value='')
        
        # Auto-update output filename when input changes
        if output_widget and postfix_widget:
            def on_input_change(change):
                if change['new']:
                    output_widget.value = generate_output_filename(change['new'], postfix_widget.value, extension)
            dropdown.observe(on_input_change, names='value')
            
            def on_postfix_change(change):
                if dropdown.value:
                    output_widget.value = generate_output_filename(dropdown.value, change['new'], extension)
            postfix_widget.observe(on_postfix_change, names='value')
        
        def on_upload(b):
            uploaded = files.upload()
            if uploaded:
                filename = list(uploaded.keys())[0]
                # Refresh ALL dropdowns so uploaded files appear everywhere
                refresh_all_dropdowns()
                # Set value on current dropdown
                dropdown.value = filename
                upload_status.value = f'✅ {filename}'
        
        upload_btn.on_click(on_upload)
        return widgets.HBox([dropdown, upload_btn, upload_status]), dropdown
    
    # Create tabs
    tab = widgets.Tab()
    
    # ===== MERGE TAB =====
    merge_postfix = widgets.Text(
        value='_merged',
        description=t['label_postfix'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='300px')
    )
    merge_output = widgets.Text(
        value='merged_output.json',
        description=t['label_output'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    merge_original_box, merge_original = create_file_picker(t['label_original'], output_widget=merge_output, postfix_widget=merge_postfix, extension='json')
    merge_helpers_box, merge_helpers = create_file_picker(t['label_helper'])
    merge_skip_sync = widgets.Checkbox(description=t['checkbox_skip_sync'], value=False)
    merge_auto_dl = widgets.Checkbox(description=t['checkbox_auto_download'], value=True)
    merge_button = widgets.Button(description=t['button_process'], button_style='primary')
    merge_output_area = widgets.Output()
    
    def on_merge_click(b):
        with merge_output_area:
            merge_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                original = merge_original.value.strip()
                helpers = [h.strip() for h in merge_helpers.value.split(',') if h.strip()]
                output = merge_output.value.strip() or 'merged_output.json'
                
                if not original or not helpers:
                    print(t['msg_no_files'])
                    return
                
                # Process
                results = process_subtitles(original, helpers, skip_sync=merge_skip_sync.value)
                
                # Save
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                print(f"{t['status_success']}")
                print(f"📁 {output}")
                print(f"📊 {len(results)} entries")
                
                # Auto download
                if merge_auto_dl.value:
                    files.download(output)
                    print(f"⬇️ Downloaded!")
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    merge_button.on_click(on_merge_click)
    
    # Output filename row with postfix
    merge_output_row = widgets.HBox([merge_output, merge_postfix])
    
    merge_tab = widgets.VBox([
        merge_original_box,
        merge_helpers_box,
        merge_output_row,
        merge_skip_sync,
        merge_auto_dl,
        merge_button,
        merge_output_area
    ], layout=widgets.Layout(padding='10px'))
    
    # ===== OVERLAPS TAB =====
    overlaps_postfix = widgets.Text(
        value='_fixed',
        description=t['label_postfix'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='300px')
    )
    overlaps_output = widgets.Text(
        value='fixed_overlaps.srt',
        description=t['label_output'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    overlaps_input_box, overlaps_input = create_file_picker(t['label_input'], output_widget=overlaps_output, postfix_widget=overlaps_postfix, extension='srt')
    overlaps_reference_box, overlaps_reference = create_file_picker(t['label_reference'])
    overlaps_window = widgets.IntSlider(
        description=t['label_window'],
        min=1, max=20, value=5,
        style={'description_width': '150px'}
    )
    overlaps_preprocess = widgets.Checkbox(description=t['checkbox_preprocess'], value=False)
    overlaps_auto_dl = widgets.Checkbox(description=t['checkbox_auto_download'], value=True)
    overlaps_button = widgets.Button(description=t['button_process'], button_style='primary')
    overlaps_output_area = widgets.Output()
    
    def on_overlaps_click(b):
        with overlaps_output_area:
            overlaps_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                input_file = overlaps_input.value.strip()
                reference = overlaps_reference.value.strip()
                output = overlaps_output.value.strip() or 'fixed_overlaps.srt'
                
                if not input_file or not reference:
                    print(t['msg_no_files'])
                    return
                
                # Process
                fix_problematic_timings(
                    input_file,
                    reference,
                    output,
                    window=overlaps_window.value,
                    preprocess=overlaps_preprocess.value
                )
                
                print(f"{t['status_success']}")
                print(f"📁 {output}")
                
                # Auto download
                if overlaps_auto_dl.value:
                    files.download(output)
                    print(f"⬇️ Downloaded!")
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    overlaps_button.on_click(on_overlaps_click)
    
    # Output filename row with postfix
    overlaps_output_row = widgets.HBox([overlaps_output, overlaps_postfix])
    
    overlaps_tab = widgets.VBox([
        overlaps_input_box,
        overlaps_reference_box,
        overlaps_output_row,
        overlaps_window,
        overlaps_preprocess,
        overlaps_auto_dl,
        overlaps_button,
        overlaps_output_area
    ], layout=widgets.Layout(padding='10px'))
    
    # ===== CORRECTIONS TAB =====
    corrections_postfix = widgets.Text(
        value='_corrected',
        description=t['label_postfix'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='300px')
    )
    corrections_output = widgets.Text(
        value='corrected.srt',
        description=t['label_output'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    corrections_input_box, corrections_input = create_file_picker(t['label_input'], output_widget=corrections_output, postfix_widget=corrections_postfix, extension='srt')
    
    # JSON file OR paste
    corrections_file_box, corrections_file = create_file_picker(t['label_corrections_file'], '*.json')
    corrections_json = widgets.Textarea(
        description=t['label_corrections_json'],
        placeholder='[{"id": 1, "rx": "find", "sb": "replace"}]',
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px', height='100px')
    )
    
    corrections_auto_dl = widgets.Checkbox(description=t['checkbox_auto_download'], value=True)
    corrections_button = widgets.Button(description=t['button_process'], button_style='primary')
    corrections_output_area = widgets.Output()
    
    def on_corrections_click(b):
        with corrections_output_area:
            corrections_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                input_file = corrections_input.value.strip()
                output = corrections_output.value.strip() or 'corrected.srt'
                
                if not input_file:
                    print(t['msg_no_files'])
                    return
                
                # Get corrections from file OR JSON paste
                corrections_data = None
                
                if corrections_json.value.strip():
                    # Parse pasted JSON
                    try:
                        corrections_data = json.loads(corrections_json.value)
                        temp_json = '_temp_corrections.json'
                        with open(temp_json, 'w', encoding='utf-8') as f:
                            json.dump(corrections_data, f)
                        corrections_file_path = temp_json
                    except json.JSONDecodeError as e:
                        print(f"{t['msg_json_error']}{e}")
                        return
                else:
                    # Use file
                    corrections_file_path = corrections_file.value.strip()
                    if not corrections_file_path:
                        print(t['msg_no_files'])
                        return
                
                # Process
                stats = apply_corrections_from_file(
                    input_file,
                    corrections_file_path,
                    output,
                    verbose=False
                )
                
                print(f"{t['status_success']}")
                print(f"📁 {output}")
                print(f"📊 {stats['applied']}/{stats['total']} corrections applied")
                
                # Auto download
                if corrections_auto_dl.value:
                    files.download(output)
                    print(f"⬇️ Downloaded!")
                
                # Cleanup temp file
                if corrections_json.value.strip() and os.path.exists('_temp_corrections.json'):
                    os.remove('_temp_corrections.json')
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    corrections_button.on_click(on_corrections_click)
    
    # Output filename row with postfix
    corrections_output_row = widgets.HBox([corrections_output, corrections_postfix])
    
    corrections_tab = widgets.VBox([
        corrections_input_box,
        corrections_file_box,
        corrections_json,
        corrections_output_row,
        corrections_auto_dl,
        corrections_button,
        corrections_output_area
    ], layout=widgets.Layout(padding='10px'))
    
    # Add tabs
    tab.children = [merge_tab, overlaps_tab, corrections_tab]
    tab.set_title(0, t['tab_merge'])
    tab.set_title(1, t['tab_overlaps'])
    tab.set_title(2, t['tab_corrections'])
    
    # Display
    display(tab)
    
    # Add usage hint
    display(HTML(f"""
    <div style="margin-top: 20px; padding: 10px; 
                background-color: var(--colab-highlighted-surface-color, #e8f0fe); 
                color: var(--colab-primary-text-color, #202124);
                border-radius: 5px; border-left: 4px solid #1a73e8;">
        <b>💡 Tip:</b> Use the file browser (left) or Upload buttons to add files. 
        Files already in /content/ will appear in the dropdown menus.
        Uploaded files will automatically appear in all tabs.
    </div>
    """))


if __name__ == '__main__':
    # Example usage in notebook
    show_ui()
