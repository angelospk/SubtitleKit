"""
Google Colab UI using ipywidgets - Enhanced version

This module provides a Jupyter/Colab-friendly interface for subtitle processing
with file pickers, JSON paste, and better dark mode support.
"""
import ipywidgets as widgets
from IPython.display import display, HTML, Javascript
from google.colab import files
import json
import os
import glob
import shutil


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
    
    # Try to import optional apply_annotations
    try:
        from subtitlekit.tools.apply_annotations import (
            load_json, apply_annotations_to_entries, entries_to_srt
        )
        has_annotations = True
    except ImportError:
        has_annotations = False
    
    # Translations
    translations = {
        'en': {
            'title': '📝 SubtitleKit - Subtitle Processing',
            'tab_merge': 'Merge Subtitles',
            'tab_overlaps': 'Fix Overlaps',
            'tab_corrections': 'Apply Corrections',
            'tab_annotations': 'Apply Annotations',
            'label_original': 'Original subtitle:',
            'label_helper': 'Helper subtitles (comma-separated):',
            'label_input': 'Input subtitle:',
            'label_reference': 'Reference subtitle:',
            'label_corrections_file': 'Corrections file:',
            'label_corrections_json': 'Or paste JSON:',
            'label_json_data': 'Merged JSON file:',
            'label_annotations_file': 'Annotations JSON:',
            'label_annotations_json': 'Or paste annotations:',
            'label_output': 'Output filename:',
            'label_postfix': 'Output postfix:',
            'label_window': 'Window size:',
            'button_upload': '📁 Upload',
            'button_process': 'Process',
            'button_reset': '🗑️ Clear All Files',
            'button_refresh_models': '🔄 Refresh Models',
            'checkbox_skip_sync': 'Skip synchronization',
            'checkbox_preprocess': 'Preprocess input',
            'checkbox_auto_download': 'Auto-download result',
            'checkbox_lenient': 'Lenient matching (ignore timing mismatch)',
            'status_upload': 'Click Upload to select file',
            'status_processing': '⏳ Processing...',
            'status_success': '✅ Success!',
            'status_error': '❌ Error: ',
            'msg_no_files': 'Please select or upload files first',
            'msg_json_error': '❌ JSON parse error: ',
            'msg_reset': '🗑️ All files cleared!',
        },
        'el': {
            'title': '📝 SubtitleKit - Επεξεργασία Υποτίτλων',
            'tab_merge': 'Ένωση Υποτίτλων',
            'tab_overlaps': 'Διόρθωση Χρονισμών',
            'tab_corrections': 'Εφαρμογή Διορθώσεων',
            'tab_annotations': 'Εφαρμογή Annotations',
            'tab_optimizer': 'Βελτιστοποίηση (Optimizer)',
            'label_original': 'Αρχικός υπότιτλος:',
            'label_helper': 'Βοηθητικοί υπότιτλοι (με κόμμα):',
            'label_input': 'Υπότιτλος εισόδου:',
            'label_reference': 'Υπότιτλος αναφοράς:',
            'label_corrections_file': 'Αρχείο διορθώσεων:',
            'label_corrections_json': 'Ή επικόλληση JSON:',
            'label_json_data': 'Merged JSON αρχείο:',
            'label_annotations_file': 'Annotations JSON:',
            'label_annotations_json': 'Ή επικόλληση annotations:',
            'label_output': 'Όνομα αρχείου εξόδου:',
            'label_postfix': 'Κατάληξη εξόδου:',
            'label_window': 'Μέγεθος παραθύρου:',
            'label_lang': 'Γλώσσα:',
            'label_gemini_key': 'Κλειδί Gemini API:',
            'label_gemini_model': 'Μοντέλο:',
            'label_cps_target': 'Στόχος CPS:',
            'button_upload': '📁 Ανέβασμα',
            'button_process': 'Επεξεργασία',
            'button_optimize': 'Optimize',
            'button_reset': '🗑️ Καθαρισμός Αρχείων',
            'button_refresh_models': '🔄 Ανανέωση Μοντέλων',
            'checkbox_line_reduction': 'Μείωση Γραμμών',
            'checkbox_cps': 'Βελτιστοποίηση CPS',
            'checkbox_interjections': 'Αφαίρεση Επιφωνημάτων',
            'checkbox_llm': 'Σύμπτυξη μέσω AI',
            'checkbox_simplify': 'Πειραματικό: Απλοποίηση',
            'checkbox_skip_sync': 'Παράλειψη συγχρονισμού',
            'checkbox_preprocess': 'Προεπεξεργασία',
            'checkbox_auto_download': 'Αυτόματο κατέβασμα',
            'checkbox_lenient': 'Χαλαρό ταίριασμα (αγνόησε timing)',
            'status_upload': 'Κλικ για ανέβασμα',
            'status_processing': '⏳ Επεξεργασία...',
            'status_success': '✅ Επιτυχία!',
            'status_error': '❌ Σφάλμα: ',
            'msg_no_files': 'Παρακαλώ επιλέξτε ή ανεβάστε αρχεία',
            'msg_json_error': '❌ Σφάλμα JSON: ',
            'msg_reset': '🗑️ Όλα τα αρχεία διαγράφηκαν!',
            'msg_opt_phase_interjections': '🧹 Αφαίρεση επιφωνημάτων...',
            'msg_opt_phase_lines': '✂️ Μείωση γραμμών...',
            'msg_opt_phase_cps': '⏱️ Βελτιστοποίηση CPS...',
            'msg_opt_phase_llm': '🤖 Σύμπτυξη μέσω AI (αυτό μπορεί να πάρει λίγο)...',
            
            # Advanced Settings
            'acc_settings_title': '⚙️ Προχωρημένες Ρυθμίσεις',
            'label_max_lines': 'Μέγ. Γραμμές:',
            'label_max_chars': 'Μέγ. Χαρακτήρες:',
            'label_max_dur': 'Μέγ. Διάρκεια (sec):',
            'label_min_dur': 'Ελάχ. Διάρκεια (sec):',
            'label_min_gap': 'Ελάχ. Κενό (sec):',
            
            # Comparison Tab
            'tab_comparison': 'Σύγκριση',
            'comp_title': 'Ανάλυση και Σύγκριση Υποτίτλων',
            'comp_existing_file': 'Ανεβασμένο αρχείο:',
            'comp_add_to_compare': 'Φόρτωση & Ανάλυση',
            'comp_load_upload': 'Ανέβασμα νέου',
            'comp_loaded_files': 'Φορτωμένα Αρχεία:',
            'comp_analyze': 'Ανάλυση (1 Αρχείο)',
            'comp_compare': 'Σύγκριση (2+ Αρχεία)',
            'comp_export': 'Εξαγωγή CSV',
            'comp_clear': 'Καθαρισμός λίστας',
            'comp_added': 'Αναλύθηκε και προστέθηκε:',
            'comp_err_single_only': 'Παρακαλώ επιλέξτε ακριβώς ένα αρχείο.',
            'comp_err_multi_only': 'Παρακαλώ επιλέξτε τουλάχιστον δύο αρχεία.',
            'comp_cleared': 'Η λίστα σύγκρισης καθαρίστηκε.',
            
            # Chart Labels
            'chart_single_title': 'Ανάλυση: ',
            'chart_freq': 'Συχνότητα',
            'chart_cps_dist': 'Κατανομή CPS',
            'chart_line_num': 'Αριθμός Γραμμής',
            'chart_cps_per_line': 'CPS ανά Γραμμή',
            'chart_current': 'Τρέχον',
            'chart_ideal': 'Ιδανικό',
            'chart_line': 'Γραμμή',
            'chart_current_vs_ideal': 'Τρέχον έναντι Ιδανικού CPS',
            'chart_prob_percent': 'Ποσοστό Προβληματικών Γραμμών',
            'chart_comp_title': 'Σύγκριση Υποτίτλων',
            'chart_cps_dist_comp': 'Σύγκριση Κατανομής CPS',
            'chart_pos_pct': 'Θέση στο αρχείο (%)',
            'chart_cps_time_comp': 'Σύγκριση CPS διαχρονικά',
            'chart_box_comp': 'Σύγκριση Box Plot CPS',
            'chart_bar_avg': 'Μέσο CPS',
            'chart_val': 'Τιμή',
            'chart_stat_comp': 'Σύγκριση Στατιστικών',
        }
    }
    
    # Add English optimizer strings
    translations['en'].update({
        'tab_optimizer': 'Optimizer',
        'label_lang': 'Language:',
        'label_gemini_key': 'Gemini API Key:',
        'label_gemini_model': 'Model:',
        'label_cps_target': 'Target CPS:',
        'button_optimize': 'Optimize',
        'checkbox_line_reduction': 'Line Reduction',
        'checkbox_cps': 'CPS Optimization',
        'checkbox_interjections': 'Interjection Removal',
        'checkbox_llm': 'LLM Shortening',
        'checkbox_simplify': 'Experimental: Simplify',
        'msg_opt_phase_interjections': '🧹 Removing interjections...',
        'msg_opt_phase_lines': '✂️ Reducing lines...',
        'msg_opt_phase_cps': '⏱️ Optimizing CPS...',
        'msg_opt_phase_llm': '🤖 Compacting via AI (this might take a while)...',
        
        # Advanced Settings
        'acc_settings_title': '⚙️ Advanced Settings',
        'label_max_lines': 'Max Lines:',
        'label_max_chars': 'Max Chars:',
        'label_max_dur': 'Max Duration (sec):',
        'label_min_dur': 'Min Duration (sec):',
        'label_min_gap': 'Min Gap (sec):',
        
        # Comparison Tab
        'tab_comparison': 'Comparison',
        'comp_title': 'Subtitle Analysis and Comparison',
        'comp_existing_file': 'Uploaded File:',
        'comp_add_to_compare': 'Load & Analyze',
        'comp_load_upload': 'Upload New',
        'comp_loaded_files': 'Loaded Files:',
        'comp_analyze': 'Analyze (1 File)',
        'comp_compare': 'Compare (2+ Files)',
        'comp_export': 'Export CSV',
        'comp_clear': 'Clear List',
        'comp_added': 'Parsed and added:',
        'comp_err_single_only': 'Please select exactly one file for single analysis.',
        'comp_err_multi_only': 'Please select at least two files for comparison.',
        'comp_cleared': 'Comparison list cleared.',
        
        # Chart Labels
        'chart_single_title': 'Analysis: ',
        'chart_freq': 'Frequency',
        'chart_cps_dist': 'CPS Distribution',
        'chart_line_num': 'Line Number',
        'chart_cps_per_line': 'CPS per Line',
        'chart_current': 'Current',
        'chart_ideal': 'Ideal',
        'chart_line': 'Line',
        'chart_current_vs_ideal': 'Current vs Ideal CPS',
        'chart_prob_percent': 'Problematic Lines Percent',
        'chart_comp_title': 'Subtitles Comparison',
        'chart_cps_dist_comp': 'CPS Dist. Comparison',
        'chart_pos_pct': 'Position in file (%)',
        'chart_cps_time_comp': 'CPS over time comparison',
        'chart_box_comp': 'CPS Box Plot Comparison',
        'chart_bar_avg': 'Avg CPS',
        'chart_val': 'Value',
        'chart_stat_comp': 'Statistics Comparison',
    })

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
    .widget-button.danger {
        background-color: #ea4335 !important;
    }
    .output_area { 
        background-color: var(--colab-secondary-surface-color, #f8f9fa) !important;
        color: var(--colab-primary-text-color, #202124) !important;
        padding: 10px !important;
        border-radius: 4px !important;
    }
    /* Hide the extra upload text that colab adds */
    .p-Widget.jupyter-widgets.widget-upload > .widget-label { display: none !important; }
    </style>
    """))
    
    # Display title
    display(HTML(f"<h2 style='color: var(--colab-primary-text-color, #202124);'>{t['title']}</h2>"))
    
    # Shared list of all dropdowns for refreshing
    all_srt_dropdowns = []
    all_json_dropdowns = []
    
    # Global output area for reset messages
    global_output = widgets.Output()
    
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
    
    def save_and_download(filepath, auto_download):
        """Save file locally and optionally download (only once)"""
        if auto_download and os.path.exists(filepath):
            files.download(filepath)
    
    # Helper: File picker widget with direct upload
    def create_file_picker(label, file_types='*.srt', output_widget=None, postfix_widget=None, extension='srt'):
        """Create a file picker with direct upload button"""
        is_json = file_types == '*.json'
        options = [''] + sorted(glob.glob(file_types))
        
        dropdown = widgets.Dropdown(
            options=options,
            description=label,
            style={'description_width': '150px'},
            layout=widgets.Layout(width='450px')
        )
        
        # Track dropdown based on type
        if is_json:
            all_json_dropdowns.append(dropdown)
        else:
            all_srt_dropdowns.append(dropdown)
        
        # Use FileUpload widget for direct file dialog
        upload_widget = widgets.FileUpload(
            accept='.srt' if not is_json else '.json',
            multiple=False,
            description=t['button_upload'],
            button_style='info',
            layout=widgets.Layout(width='120px')
        )
        
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
        
        def on_upload_change(change):
            """Handle file upload directly"""
            if change['new']:
                for filename, file_info in change['new'].items():
                    # Save file locally
                    content = file_info['content']
                    with open(filename, 'wb') as f:
                        f.write(content)
                    
                    # Refresh ALL dropdowns
                    refresh_all_dropdowns()
                    # Set value on current dropdown
                    dropdown.value = filename
                    upload_status.value = f'✅ {filename}'
                    break
        
        upload_widget.observe(on_upload_change, names='value')
        return widgets.HBox([dropdown, upload_widget, upload_status]), dropdown
    
    # Reset button
    reset_button = widgets.Button(
        description=t['button_reset'], 
        button_style='danger',
        layout=widgets.Layout(width='200px')
    )
    
    def on_reset_click(b):
        with global_output:
            global_output.clear_output()
            # Delete all .srt and .json files in current directory
            for f in glob.glob('*.srt') + glob.glob('*.json'):
                try:
                    os.remove(f)
                except:
                    pass
            refresh_all_dropdowns()
            print(t['msg_reset'])
    
    reset_button.on_click(on_reset_click)
    
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
                helpers_str = merge_helpers.value.strip()
                helpers = [h.strip() for h in helpers_str.split(',') if h.strip()] if helpers_str else None
                output = merge_output.value.strip() or 'merged_output.json'
                
                if not original:
                    print(t['msg_no_files'])
                    return
                
                # Process (works with or without helpers)
                result = process_subtitles(original, helpers, skip_sync=merge_skip_sync.value)
                
                # Extract data
                entries = result.get('entries', [])
                preprocessing = result.get('preprocessing', {})
                preprocessed_path = result.get('preprocessed_path')
                
                # Save JSON locally
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
                
                print(f"{t['status_success']}")
                print(f"📁 Saved JSON: {output}")
                print(f"📊 {len(entries)} entries")
                
                # Show preprocessing info
                if preprocessing.get('preprocessed'):
                    print(f"✨ Preprocessed: {preprocessing['total_entries']} subtitles")
                    if preprocessed_path:
                        print(f"📄 Preprocessed SRT: {preprocessed_path}")
                
                # Show mode info
                if not helpers:
                    print("ℹ️  Mode: Standalone (preprocessing only, no helpers)")
                else:
                    print(f"ℹ️  Mode: Merged with {len(helpers)} helper file(s)")
                
                # Refresh dropdowns so new files appear
                refresh_all_dropdowns()
                
                # Download if requested (only once)
                if merge_auto_dl.value:
                    files.download(output)
                
            except Exception as e:
                import traceback
                print(f"{t['status_error']}{e}")
                print(traceback.format_exc())
    
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
                print(f"📁 Saved: {output}")
                
                # Refresh dropdowns
                refresh_all_dropdowns()
                
                # Download if requested (only once)
                if overlaps_auto_dl.value:
                    files.download(output)
                
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
                print(f"📁 Saved: {output}")
                print(f"📊 {stats['applied']}/{stats['total']} corrections applied")
                
                # Refresh dropdowns
                refresh_all_dropdowns()
                
                # Download if requested (only once)
                if corrections_auto_dl.value:
                    files.download(output)
                
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
    
    # ===== ANNOTATIONS TAB =====
    annotations_postfix = widgets.Text(
        value='_annotated',
        description=t['label_postfix'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='300px')
    )
    annotations_output = widgets.Text(
        value='annotated.srt',
        description=t['label_output'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    annotations_json_box, annotations_json_file = create_file_picker(
        t['label_json_data'], '*.json', 
        output_widget=annotations_output, postfix_widget=annotations_postfix, extension='srt'
    )
    annotations_file_box, annotations_file = create_file_picker(t['label_annotations_file'], '*.json')
    annotations_paste = widgets.Textarea(
        description=t['label_annotations_json'],
        placeholder='[{"id": 1, "t": "00:00:01,000 --> 00:00:02,000", "note": "{M} male speaker"}]',
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px', height='100px')
    )
    annotations_lenient = widgets.Checkbox(description=t['checkbox_lenient'], value=False)
    annotations_auto_dl = widgets.Checkbox(description=t['checkbox_auto_download'], value=True)
    annotations_button = widgets.Button(description=t['button_process'], button_style='primary')
    annotations_output_area = widgets.Output()
    
    def on_annotations_click(b):
        with annotations_output_area:
            annotations_output_area.clear_output()
            
            if not has_annotations:
                print("❌ apply_annotations module not available. Update subtitlekit.")
                return
            
            print(t['status_processing'])
            
            try:
                json_data_file = annotations_json_file.value.strip()
                output = annotations_output.value.strip() or 'annotated.srt'
                
                if not json_data_file:
                    print(t['msg_no_files'])
                    return
                
                # Load JSON data
                entries = load_json(json_data_file)
                
                # Get annotations from file OR paste
                if annotations_paste.value.strip():
                    try:
                        annotations = json.loads(annotations_paste.value)
                    except json.JSONDecodeError as e:
                        print(f"{t['msg_json_error']}{e}")
                        return
                else:
                    ann_file = annotations_file.value.strip()
                    if not ann_file:
                        print(t['msg_no_files'])
                        return
                    annotations = load_json(ann_file)
                
                # Apply annotations
                modified_entries, stats = apply_annotations_to_entries(
                    entries, annotations, strict=not annotations_lenient.value
                )
                
                # Convert to SRT
                srt_content = entries_to_srt(modified_entries)
                with open(output, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                
                print(f"{t['status_success']}")
                print(f"📁 Saved: {output}")
                print(f"✓ Matched: {stats['matched']}/{len(annotations)}")
                
                if stats['mismatched']:
                    print(f"⚠ Mismatched: {len(stats['mismatched'])}")
                
                # Refresh dropdowns
                refresh_all_dropdowns()
                
                # Download if requested (only once)
                if annotations_auto_dl.value:
                    files.download(output)
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    annotations_button.on_click(on_annotations_click)
    
    # Output filename row with postfix
    annotations_output_row = widgets.HBox([annotations_output, annotations_postfix])
    
    annotations_tab = widgets.VBox([
        annotations_json_box,
        annotations_file_box,
        annotations_paste,
        annotations_output_row,
        annotations_lenient,
        annotations_auto_dl,
        annotations_button,
        annotations_output_area
    ], layout=widgets.Layout(padding='10px'))
    
    # ===== OPTIMIZER TAB =====
    opt_postfix = widgets.Text(
        value='_optimized',
        description=t['label_postfix'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='300px')
    )
    opt_output = widgets.Text(
        value='optimized.srt',
        description=t['label_output'],
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    opt_input_box, opt_input = create_file_picker(
        t['label_input'], output_widget=opt_output, 
        postfix_widget=opt_postfix, extension='srt'
    )
    
    # Optimizer settings from config
    from subtitlekit.optimizer.config import get_setting, set_setting
    
    # Try to load API key from Colab secrets if available
    default_key = get_setting('gemini_api_key', '')
    try:
        from google.colab import userdata
        colab_key = userdata.get('GEMINI_API_KEY')
        if colab_key:
            default_key = colab_key
    except Exception:
        pass
    
    opt_api_key = widgets.Password(
        description=t['label_gemini_key'],
        value=default_key,
        style={'description_width': '150px'},
        layout=widgets.Layout(width='500px')
    )
    
    opt_model = widgets.Dropdown(
        description=t['label_gemini_model'],
        options=[get_setting('gemini_model', 'gemini-2.0-flash')],
        value=get_setting('gemini_model', 'gemini-2.0-flash'),
        style={'description_width': '150px'},
        layout=widgets.Layout(width='350px')
    )
    
    opt_refresh_btn = widgets.Button(
        description=t['button_refresh_models'],
        button_style='info',
        tooltip='Fetch available models from Gemini API',
        layout=widgets.Layout(width='150px')
    )
    
    opt_cps_target = widgets.FloatText(
        description=t['label_cps_target'],
        value=get_setting('cps_target', 20.0),
        style={'description_width': '150px'},
        layout=widgets.Layout(width='200px')
    )

    opt_lang_code = widgets.Dropdown(
        description=t['label_lang'],
        options=['en', 'el', 'es', 'fr', 'de'],
        value='en',
        style={'description_width': '150px'},
        layout=widgets.Layout(width='200px')
    )
    
    opt_line_red = widgets.Checkbox(description=t['checkbox_line_reduction'], value=True)
    opt_cps_opt = widgets.Checkbox(description=t['checkbox_cps'], value=True)
    opt_inter_rem = widgets.Checkbox(description=t['checkbox_interjections'], value=True)
    opt_llm_short = widgets.Checkbox(description=t['checkbox_llm'], value=False)
    opt_simpl = widgets.Checkbox(description=t['checkbox_simplify'], value=False)
    
    # Advanced settings (Accordion)
    opt_max_lines = widgets.IntText(value=2, description=t['label_max_lines'], style={'description_width': 'initial'}, layout=widgets.Layout(width='150px'))
    opt_max_chars = widgets.IntText(value=90, description=t['label_max_chars'], style={'description_width': 'initial'}, layout=widgets.Layout(width='150px'))
    opt_max_dur = widgets.FloatText(value=7.0, description=t['label_max_dur'], style={'description_width': 'initial'}, layout=widgets.Layout(width='180px'))
    opt_min_dur = widgets.FloatText(value=0.833, description=t['label_min_dur'], style={'description_width': 'initial'}, layout=widgets.Layout(width='180px'))
    opt_min_gap = widgets.FloatText(value=0.12, description=t['label_min_gap'], style={'description_width': 'initial'}, layout=widgets.Layout(width='150px'))
    
    advanced_settings_box = widgets.VBox([
        widgets.HBox([opt_max_lines, opt_max_chars]),
        widgets.HBox([opt_max_dur, opt_min_dur, opt_min_gap])
    ])
    
    opt_advanced_accordion = widgets.Accordion(children=[advanced_settings_box])
    opt_advanced_accordion.set_title(0, t['acc_settings_title'])
    opt_advanced_accordion.selected_index = None # Start closed
    
    opt_auto_dl = widgets.Checkbox(description=t['checkbox_auto_download'], value=True)
    opt_button = widgets.Button(description=t['button_optimize'], button_style='primary')
    opt_output_area = widgets.Output()

    def fetch_models(b=None):
        """Fetch available Gemini models synchronously so ipywidgets updates correctly."""
        key = opt_api_key.value.strip()
        if not key: return
        
        # Give visual feedback that it's fetching
        old_desc = opt_refresh_btn.description
        opt_refresh_btn.description = "⏳..."
        
        try:
            from google import genai
            client = genai.Client(api_key=key)
            models = [m.name.replace("models/", "") for m in client.models.list() if "gemini" in m.name.lower()]
            if models:
                opt_model.options = sorted(list(set(models + [opt_model.value])))
        except Exception as e:
            print(f"Error fetching models: {e}")
        finally:
            opt_refresh_btn.description = old_desc

    opt_api_key.observe(lambda change: fetch_models() if change['new'] else None, names='value')
    opt_refresh_btn.on_click(lambda b: fetch_models())

    def on_optimize_click(b):
        with opt_output_area:
            opt_output_area.clear_output()
            print(t['status_processing'])
            
            # Save settings
            set_setting('gemini_api_key', opt_api_key.value)
            set_setting('gemini_model', opt_model.value)
            set_setting('cps_target', opt_cps_target.value)

            try:
                input_file = opt_input.value.strip()
                output = opt_output.value.strip() or 'optimized.srt'
                
                if not input_file:
                    print(t['msg_no_files'])
                    return
                
                import pysrt
                from subtitlekit.optimizer import OptimizerPipeline, OptimizationOptions
                
                options = OptimizationOptions(
                    line_reduction=opt_line_red.value,
                    cps_optimization=opt_cps_opt.value,
                    interjection_removal=opt_inter_rem.value,
                    llm_shortening=opt_llm_short.value,
                    simplify=opt_simpl.value,
                    lang=opt_lang_code.value,
                    cps_target=opt_cps_target.value,
                    max_lines=opt_max_lines.value,
                    max_chars=opt_max_chars.value,
                    max_duration=opt_max_dur.value,
                    min_duration=opt_min_dur.value,
                    min_gap=opt_min_gap.value,
                    api_key=opt_api_key.value,
                    model=opt_model.value
                )
                
                subs = pysrt.open(input_file)
                pipeline = OptimizerPipeline(
                    options,
                    progress_callback=lambda phase: print(t.get(f'msg_opt_phase_{phase}', phase))
                )
                results = pipeline.run(subs)
                results.save(output, encoding='utf-8')
                
                print(f"{t['status_success']}")
                print(f"📁 Saved: {output}")
                
                refresh_all_dropdowns()
                if opt_auto_dl.value:
                    files.download(output)
                
            except Exception as e:
                print(f"{t['status_error']}{e}")
    
    opt_button.on_click(on_optimize_click)
    
    opt_tab = widgets.VBox([
        opt_input_box,
        opt_output,
        opt_api_key,
        widgets.HBox([opt_model, opt_refresh_btn]),
        widgets.HBox([opt_cps_target, opt_lang_code]),
        widgets.VBox([opt_line_red, opt_cps_opt, opt_inter_rem, opt_llm_short, opt_simpl]),
        opt_advanced_accordion,
        opt_auto_dl,
        opt_button,
        opt_output_area
    ], layout=widgets.Layout(padding='10px'))

    # ---------------------------------------------------------
    # Comparison Tab
    # ---------------------------------------------------------
    from subtitlekit.tools.subtitle_stats import SubtitleStorage, analyze_subtitles_from_bytes, create_single_file_chart, create_comparison_chart
    import matplotlib.pyplot as plt
    
    comp_storage = SubtitleStorage()
    
    comp_title = widgets.HTML(f"<h3 style='color: var(--colab-primary-text-color, #202124);'>{t['comp_title']}</h3>")
    
    # Upload new file
    comp_upload = widgets.FileUpload(accept='.srt', multiple=False, description=t['comp_load_upload'])
    
    # Load from existing dropdown
    comp_existing_dropdown = widgets.Dropdown(options=[''] + sorted(glob.glob('*.srt')), description=t['comp_existing_file'])
    all_srt_dropdowns.append(comp_existing_dropdown)
    comp_load_existing_btn = widgets.Button(description=t['comp_add_to_compare'], button_style='primary')
    
    comp_loaded_list = widgets.SelectMultiple(options=[], description=t['comp_loaded_files'], layout={'width': 'max-content'})
    
    comp_analyze_btn = widgets.Button(description=t['comp_analyze'], button_style='success')
    comp_compare_btn = widgets.Button(description=t['comp_compare'], button_style='warning')
    comp_export_btn = widgets.Button(description=t['comp_export'])
    comp_clear_btn = widgets.Button(description=t['comp_clear'], button_style='danger')
    
    comp_output = widgets.Output()
    
    def refresh_comp_list():
        comp_loaded_list.options = comp_storage.list_files()
        
    def on_comp_load_existing(b):
        file_path = comp_existing_dropdown.value
        if not file_path: return
        with comp_output:
            comp_output.clear_output()
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                df, stats = analyze_subtitles_from_bytes(content, file_path)
                comp_storage.add(file_path, content, df, stats)
                refresh_comp_list()
                print(f"✅ {t['comp_added']} {file_path}")
            except Exception as e:
                print(f"❌ Error: {e}")
                
    comp_load_existing_btn.on_click(on_comp_load_existing)
    
    def on_comp_upload(change):
        if not comp_upload.value: return
        # Same upload logic as other tabs
        # Handle dict format in older ipywidgets or newer
        try:
            items = comp_upload.value.items()
        except AttributeError:
            items = [(comp_upload.value[0]['name'], comp_upload.value[0])]
            
        for filename, file_info in items:
            content = file_info['content'] if isinstance(file_info, dict) and 'content' in file_info else file_info
            with open(filename, 'wb') as f:
                f.write(content)
            
            with comp_output:
                try:
                    df, stats = analyze_subtitles_from_bytes(content, filename)
                    comp_storage.add(filename, content, df, stats)
                    refresh_comp_list()
                    print(f"✅ {t['comp_added']} {filename}")
                except Exception as e:
                    print(f"❌ Error: {e}")
                    
        comp_upload.value.clear()
        refresh_all_dropdowns()  # Important: refresh everywhere
        
    comp_upload.observe(on_comp_upload, names='value')

    def on_comp_analyze(b):
        selected = comp_loaded_list.value
        with comp_output:
            comp_output.clear_output()
            if not selected:
                print(t['msg_no_files'])
                return
            if len(selected) > 1:
                print(t['comp_err_single_only'])
                return
            sub_data = comp_storage.get(selected[0])
            if sub_data:
                fig = create_single_file_chart(sub_data, t)
                plt.show(fig)
                
    comp_analyze_btn.on_click(on_comp_analyze)
    
    def on_comp_compare(b):
        selected = comp_loaded_list.value
        with comp_output:
            comp_output.clear_output()
            if len(selected) < 2:
                print(t['comp_err_multi_only'])
                return
            data_list = [comp_storage.get(f) for f in selected if comp_storage.get(f)]
            if data_list:
                fig = create_comparison_chart(data_list, t)
                plt.show(fig)
                
    comp_compare_btn.on_click(on_comp_compare)
    
    def on_comp_export(b):
        selected = comp_loaded_list.value
        with comp_output:
            if not selected: return
            for f in selected:
                sub_data = comp_storage.get(f)
                csv_path = f"{os.path.splitext(f)[0]}_analysis.csv"
                sub_data.dataframe.to_csv(csv_path, index=False)
                print(f"✅ Exported: {csv_path}")
                files.download(csv_path)

    comp_export_btn.on_click(on_comp_export)
    
    def on_comp_clear(b):
        comp_storage.clear()
        refresh_comp_list()
        with comp_output:
            comp_output.clear_output()
            print(t['comp_cleared'])
            
    comp_clear_btn.on_click(on_comp_clear)
    
    comp_tab = widgets.VBox([
        comp_title,
        widgets.HBox([comp_existing_dropdown, comp_load_existing_btn]),
        widgets.HBox([comp_upload]),
        widgets.HTML("<hr>"),
        widgets.HBox([comp_loaded_list, widgets.VBox([comp_analyze_btn, comp_compare_btn, comp_export_btn, comp_clear_btn])]),
        comp_output
    ], layout=widgets.Layout(padding='10px'))

    # Add tabs
    tab_children = [merge_tab, overlaps_tab, corrections_tab, opt_tab, comp_tab]
    tab_titles = [t['tab_merge'], t['tab_overlaps'], t['tab_corrections'], t['tab_optimizer'], t['tab_comparison']]
    
    if has_annotations:
        tab_children.append(annotations_tab)
        tab_titles.append(t['tab_annotations'])
    
    tab.children = tab_children
    for i, title in enumerate(tab_titles):
        tab.set_title(i, title)
    
    # Display reset button and tabs
    display(widgets.HBox([reset_button, global_output]))
    display(tab)
    
    # Add usage hint
    display(HTML(f"""
    <div style="margin-top: 20px; padding: 10px; 
                background-color: var(--colab-highlighted-surface-color, #e8f0fe); 
                color: var(--colab-primary-text-color, #202124);
                border-radius: 5px; border-left: 4px solid #1a73e8;">
        <b>💡 Tips:</b><br>
        • Click the blue "📁 Upload" button to select a file directly<br>
        • Files are saved locally and appear in all tabs<br>
        • Use "🗑️ Clear All Files" to reset and start fresh
    </div>
    """))


if __name__ == '__main__':
    # Example usage in notebook
    show_ui()
