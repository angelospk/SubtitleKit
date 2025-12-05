"""
Google Colab UI using ipywidgets

This module provides a Jupyter/Colab-friendly interface for subtitle processing.
"""
import ipywidgets as widgets
from IPython.display import display, HTML
import json
import os


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
            'label_original': 'Original subtitle path:',
            'label_helper': 'Helper subtitle paths (comma-separated):',
            'label_input': 'Input subtitle path:',
            'label_reference': 'Reference subtitle path:',
            'label_corrections': 'Corrections JSON path:',
            'label_output': 'Output file path:',
            'label_window': 'Window size:',
            'button_process': 'Process',
            'checkbox_skip_sync': 'Skip synchronization',
            'checkbox_preprocess': 'Preprocess input',
            'status_processing': '⏳ Processing...',
            'status_success': '✅ Success! Output saved.',
            'status_error': '❌ Error: ',
        },
        'el': {
            'title': '📝 SubtitleKit - Επεξεργασία Υποτίτλων',
            'tab_merge': 'Ένωση Υποτίτλων',
            'tab_overlaps': 'Διόρθωση Χρονισμών',
            'tab_corrections': 'Εφαρμογή Διορθώσεων',
            'label_original': 'Αρχικός υπότιτλος:',
            'label_helper': 'Βοηθητικοί υπότιτλοι (διαχωρισμένοι με κόμμα):',
            'label_input': 'Υπότιτλος εισόδου:',
            'label_reference': 'Υπότιτλος αναφοράς:',
            'label_corrections': 'Διορθώσεις JSON:',
            'label_output': 'Αρχείο εξόδου:',
            'label_window': 'Μέγεθος παραθύρου:',
            'button_process': 'Επεξεργασία',
            'checkbox_skip_sync': 'Παράλειψη συγχρονισμού',
            'checkbox_preprocess': 'Προεπεξεργασία',
            'status_processing': '⏳ Επεξεργασία...',
            'status_success': '✅ Επιτυχία! Το αποτέλεσμα αποθηκεύτηκε.',
            'status_error': '❌ Σφάλμα: ',
        }
    }
    
    t = translations.get(lang, translations['en'])
    
    # Display title
    display(HTML(f"<h2>{t['title']}</h2>"))
    
    # Create tabs
    tab = widgets.Tab()
    
    # ===== MERGE TAB =====
    merge_original = widgets.Text(description=t['label_original'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    merge_helpers = widgets.Text(description=t['label_helper'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    merge_output = widgets.Text(description=t['label_output'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    merge_skip_sync = widgets.Checkbox(description=t['checkbox_skip_sync'], value=False)
    merge_button = widgets.Button(description=t['button_process'], button_style='primary')
    merge_output_area = widgets.Output()
    
    def on_merge_click(b):
        with merge_output_area:
            merge_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                original = merge_original.value.strip()
                helpers = [h.strip() for h in merge_helpers.value.split(',') if h.strip()]
                output = merge_output.value.strip()
                
                if not original or not helpers or not output:
                    print("❌ Please fill all fields")
                    return
                
                # Process
                results = process_subtitles(original, helpers, skip_sync=merge_skip_sync.value)
                
                # Save
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                print(f"{t['status_success']}")
                print(f"📁 Output: {output}")
                print(f"📊 Processed {len(results)} entries")
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    merge_button.on_click(on_merge_click)
    
    merge_tab = widgets.VBox([
        merge_original,
        merge_helpers,
        merge_output,
        merge_skip_sync,
        merge_button,
        merge_output_area
    ])
    
    # ===== OVERLAPS TAB =====
    overlaps_input = widgets.Text(description=t['label_input'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    overlaps_reference = widgets.Text(description=t['label_reference'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    overlaps_output = widgets.Text(description=t['label_output'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    overlaps_window = widgets.IntSlider(description=t['label_window'], min=1, max=20, value=5, style={'description_width': '200px'})
    overlaps_preprocess = widgets.Checkbox(description=t['checkbox_preprocess'], value=False)
    overlaps_button = widgets.Button(description=t['button_process'], button_style='primary')
    overlaps_output_area = widgets.Output()
    
    def on_overlaps_click(b):
        with overlaps_output_area:
            overlaps_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                input_file = overlaps_input.value.strip()
                reference = overlaps_reference.value.strip()
                output = overlaps_output.value.strip()
                
                if not input_file or not reference or not output:
                    print("❌ Please fill all fields")
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
                print(f"📁 Output: {output}")
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    overlaps_button.on_click(on_overlaps_click)
    
    overlaps_tab = widgets.VBox([
        overlaps_input,
        overlaps_reference,
        overlaps_output,
        overlaps_window,
        overlaps_preprocess,
        overlaps_button,
        overlaps_output_area
    ])
    
    # ===== CORRECTIONS TAB =====
    corrections_input = widgets.Text(description=t['label_input'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    corrections_json = widgets.Text(description=t['label_corrections'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    corrections_output = widgets.Text(description=t['label_output'], style={'description_width': '200px'}, layout=widgets.Layout(width='600px'))
    corrections_button = widgets.Button(description=t['button_process'], button_style='primary')
    corrections_output_area = widgets.Output()
    
    def on_corrections_click(b):
        with corrections_output_area:
            corrections_output_area.clear_output()
            print(t['status_processing'])
            
            try:
                input_file = corrections_input.value.strip()
                corrections_file = corrections_json.value.strip()
                output = corrections_output.value.strip()
                
                if not input_file or not corrections_file or not output:
                    print("❌ Please fill all fields")
                    return
                
                # Process
                stats = apply_corrections_from_file(
                    input_file,
                    corrections_file,
                    output,
                    verbose=False
                )
                
                print(f"{t['status_success']}")
                print(f"📁 Output: {output}")
                print(f"📊 Applied: {stats['applied']}/{stats['total']} corrections")
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    corrections_button.on_click(on_corrections_click)
    
    corrections_tab = widgets.VBox([
        corrections_input,
        corrections_json,
        corrections_output,
        corrections_button,
        corrections_output_area
    ])
    
    # Add tabs
    tab.children = [merge_tab, overlaps_tab, corrections_tab]
    tab.set_title(0, t['tab_merge'])
    tab.set_title(1, t['tab_overlaps'])
    tab.set_title(2, t['tab_corrections'])
    
    # Display
    display(tab)
    
    # Add usage hint
    display(HTML("""
    <div style="margin-top: 20px; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">
        <b>💡 Tip:</b> You can upload files to Colab using the file browser on the left, or use Google Drive paths like <code>/content/drive/MyDrive/...</code>
    </div>
    """))


if __name__ == '__main__':
    # Example usage in notebook
    show_ui()
