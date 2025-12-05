#!/usr/bin/env python3
"""
SubtitleKit Desktop UI - Tkinter Application

Simple, lightweight desktop application for subtitle processing.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
from pathlib import Path
import threading


# Import subtitlekit functions
try:
    from subtitlekit import merge_subtitles, fix_overlaps, apply_corrections, __version__
    from subtitlekit.updater import check_for_updates
except ImportError:
    # Fallback for development
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from subtitlekit import merge_subtitles, fix_overlaps, apply_corrections, __version__
    from subtitlekit.updater import check_for_updates


class I18n:
    """Simple internationalization"""
    def __init__(self, lang='en'):
        self.lang = lang
        self.translations = {}
        self.load_translations()
    
    def load_translations(self):
        """Load translation file"""
        locale_dir = Path(__file__).parent / 'locales'
        locale_file = locale_dir / f'{self.lang}.json'
        
        if locale_file.exists():
            with open(locale_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        else:
            # Fallback to English defaults if file not found
            print(f"Warning: Locale file {locale_file} not found, using defaults")
            self.translations = {}
    
    def t(self, key, **kwargs):
        """Translate key"""
        text = self.translations.get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text


class SubtitleKitApp:
    def __init__(self, root):
        self.root = root
        self.i18n = I18n('en')  # Default to English
        
        # Setup window
        self.root.title(self.i18n.t('app_title'))
        self.root.geometry('800x600')
        
        # Variables
        self.helper_files = []
        
        # Create UI
        self.create_menu()
        self.create_tabs()
        self.create_status_bar()
        
        # Check for updates on startup (async)
        threading.Thread(target=self.check_updates_silent, daemon=True).start()
    
    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.i18n.t('menu_file'), menu=file_menu)
        file_menu.add_command(label=self.i18n.t('menu_exit'), command=self.root.quit)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.i18n.t('menu_help'), menu=help_menu)
        help_menu.add_command(label=self.i18n.t('menu_about'), command=self.show_about)
        help_menu.add_command(label=self.i18n.t('menu_check_updates'), command=self.check_updates)
    
    def create_tabs(self):
        """Create tab interface"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create frames for each tab
        self.merge_frame = ttk.Frame(self.notebook)
        self.overlaps_frame = ttk.Frame(self.notebook)
        self.corrections_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.merge_frame, text=self.i18n.t('tab_merge'))
        self.notebook.add(self.overlaps_frame, text=self.i18n.t('tab_overlaps'))
        self.notebook.add(self.corrections_frame, text=self.i18n.t('tab_corrections'))
        
        # Build each tab
        self.build_merge_tab()
        self.build_overlaps_tab()
        self.build_corrections_tab()
    
    def build_merge_tab(self):
        """Build merge subtitles tab"""
        frame = self.merge_frame
        
        # Original file
        ttk.Label(frame, text=self.i18n.t('label_original')).grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.merge_original = ttk.Entry(frame, width=50)
        self.merge_original.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_file(self.merge_original, [('SRT files', '*.srt')])).grid(row=0, column=2, padx=5)
        
        # Helper files (listbox)
        ttk.Label(frame, text=self.i18n.t('label_helper')).grid(row=1, column=0, sticky='nw', padx=5, pady=5)
        self.helper_listbox = tk.Listbox(frame, height=4, width=50)
        self.helper_listbox.grid(row=1, column=1, padx=5, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=2, padx=5)
        ttk.Button(btn_frame, text=self.i18n.t('button_add_helper'), 
                  command=self.add_helper_file).pack(fill='x', pady=2)
        ttk.Button(btn_frame, text=self.i18n.t('button_remove_helper'), 
                  command=self.remove_helper_file).pack(fill='x', pady=2)
        
        # Output file
        ttk.Label(frame, text=self.i18n.t('label_output')).grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.merge_output = ttk.Entry(frame, width=50)
        self.merge_output.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_save_file(self.merge_output, [('JSON files', '*.json')])).grid(row=2, column=2, padx=5)
        
        # Options
        self.merge_skip_sync = tk.BooleanVar()
        ttk.Checkbutton(frame, text=self.i18n.t('checkbox_skip_sync'), 
                       variable=self.merge_skip_sync).grid(row=3, column=1, sticky='w', padx=5)
        
        # Process button
        ttk.Button(frame, text=self.i18n.t('button_process'), 
                  command=self.process_merge).grid(row=4, column=1, pady=20)
    
    def build_overlaps_tab(self):
        """Build fix overlaps tab"""
        frame = self.overlaps_frame
        
        # Input file
        ttk.Label(frame, text=self.i18n.t('label_input')).grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.overlaps_input = ttk.Entry(frame, width=50)
        self.overlaps_input.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_file(self.overlaps_input, [('SRT files', '*.srt')])).grid(row=0, column=2, padx=5)
        
        # Reference file
        ttk.Label(frame, text=self.i18n.t('label_reference')).grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.overlaps_reference = ttk.Entry(frame, width=50)
        self.overlaps_reference.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_file(self.overlaps_reference, [('SRT files', '*.srt')])).grid(row=1, column=2, padx=5)
        
        # Output file
        ttk.Label(frame, text=self.i18n.t('label_output')).grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.overlaps_output = ttk.Entry(frame, width=50)
        self.overlaps_output.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_save_file(self.overlaps_output, [('SRT files', '*.srt')])).grid(row=2, column=2, padx=5)
        
        # Window size
        ttk.Label(frame, text=self.i18n.t('label_window')).grid(row=3, column=0, sticky='w', padx=5, pady=5)
        self.overlaps_window = ttk.Spinbox(frame, from_=1, to=20, width=10)
        self.overlaps_window.set(5)
        self.overlaps_window.grid(row=3, column=1, sticky='w', padx=5, pady=5)
        
        # Options
        self.overlaps_preprocess = tk.BooleanVar()
        ttk.Checkbutton(frame, text=self.i18n.t('checkbox_preprocess'), 
                       variable=self.overlaps_preprocess).grid(row=4, column=1, sticky='w', padx=5)
        
        # Process button
        ttk.Button(frame, text=self.i18n.t('button_process'), 
                  command=self.process_overlaps).grid(row=5, column=1, pady=20)
    
    def build_corrections_tab(self):
        """Build apply corrections tab"""
        frame = self.corrections_frame
        
        # Input file
        ttk.Label(frame, text=self.i18n.t('label_input')).grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.corrections_input = ttk.Entry(frame, width=50)
        self.corrections_input.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_file(self.corrections_input, [('SRT files', '*.srt')])).grid(row=0, column=2, padx=5)
        
        # Corrections JSON
        ttk.Label(frame, text=self.i18n.t('label_corrections')).grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.corrections_json = ttk.Entry(frame, width=50)
        self.corrections_json.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_file(self.corrections_json, [('JSON files', '*.json')])).grid(row=1, column=2, padx=5)
        
        # Output file
        ttk.Label(frame, text=self.i18n.t('label_output')).grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.corrections_output = ttk.Entry(frame, width=50)
        self.corrections_output.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(frame, text=self.i18n.t('button_browse'), 
                  command=lambda: self.browse_save_file(self.corrections_output, [('SRT files', '*.srt')])).grid(row=2, column=2, padx=5)
        
        # Options
        self.corrections_quiet = tk.BooleanVar()
        ttk.Checkbutton(frame, text=self.i18n.t('checkbox_quiet'), 
                       variable=self.corrections_quiet).grid(row=3, column=1, sticky='w', padx=5)
        
        # Process button
        ttk.Button(frame, text=self.i18n.t('button_process'), 
                  command=self.process_corrections).grid(row=4, column=1, pady=20)
    
    def create_status_bar(self):
        """Create status bar at bottom"""
        self.status_bar = ttk.Label(self.root, text=self.i18n.t('status_ready'), relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def browse_file(self, entry_widget, filetypes):
        """Browse for input file"""
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)
    
    def browse_save_file(self, entry_widget, filetypes):
        """Browse for output file"""
        filename = filedialog.asksaveasfilename(filetypes=filetypes, defaultextension=filetypes[0][1])
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)
    
    def add_helper_file(self):
        """Add helper file to list"""
        filename = filedialog.askopenfilename(filetypes=[('SRT files', '*.srt')])
        if filename:
            self.helper_files.append(filename)
            self.helper_listbox.insert(tk.END, os.path.basename(filename))
    
    def remove_helper_file(self):
        """Remove selected helper file"""
        selection = self.helper_listbox.curselection()
        if selection:
            idx = selection[0]
            self.helper_listbox.delete(idx)
            self.helper_files.pop(idx)
    
    def process_merge(self):
        """Process merge operation"""
        original = self.merge_original.get()
        output = self.merge_output.get()
        
        if not original or not self.helper_files or not output:
            messagebox.showerror("Error", self.i18n.t('msg_select_files'))
            return
        
        # Run in thread to avoid freezing UI
        def run():
            try:
                self.status_bar.config(text=self.i18n.t('status_processing'))
                from subtitlekit.tools.matcher import process_subtitles
                
                results = process_subtitles(
                    original,
                    self.helper_files,
                    skip_sync=self.merge_skip_sync.get()
                )
                
                # Save output
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                
                self.status_bar.config(text=self.i18n.t('status_success'))
                messagebox.showinfo("Success", self.i18n.t('msg_complete', path=output))
                
            except Exception as e:
                self.status_bar.config(text=self.i18n.t('status_error'))
                messagebox.showerror("Error", self.i18n.t('msg_error', error=str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def process_overlaps(self):
        """Process overlaps correction"""
        input_file = self.overlaps_input.get()
        reference = self.overlaps_reference.get()
        output = self.overlaps_output.get()
        
        if not input_file or not reference or not output:
            messagebox.showerror("Error", self.i18n.t('msg_select_files'))
            return
        
        def run():
            try:
                self.status_bar.config(text=self.i18n.t('status_processing'))
                from subtitlekit.tools.overlaps import fix_problematic_timings
                
                fix_problematic_timings(
                    input_file,
                    reference,
                    output,
                    window=int(self.overlaps_window.get()),
                    preprocess=self.overlaps_preprocess.get()
                )
                
                self.status_bar.config(text=self.i18n.t('status_success'))
                messagebox.showinfo("Success", self.i18n.t('msg_complete', path=output))
                
            except Exception as e:
                self.status_bar.config(text=self.i18n.t('status_error'))
                messagebox.showerror("Error", self.i18n.t('msg_error', error=str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def process_corrections(self):
        """Process corrections application"""
        input_file = self.corrections_input.get()
        corrections_file = self.corrections_json.get()
        output = self.corrections_output.get()
        
        if not input_file or not corrections_file or not output:
            messagebox.showerror("Error", self.i18n.t('msg_select_files'))
            return
        
        def run():
            try:
                self.status_bar.config(text=self.i18n.t('status_processing'))
                from subtitlekit.tools.corrections import apply_corrections_from_file
                
                apply_corrections_from_file(
                    input_file,
                    corrections_file,
                    output,
                    verbose=not self.corrections_quiet.get()
                )
                
                self.status_bar.config(text=self.i18n.t('status_success'))
                messagebox.showinfo("Success", self.i18n.t('msg_complete', path=output))
                
            except Exception as e:
                self.status_bar.config(text=self.i18n.t('status_error'))
                messagebox.showerror("Error", self.i18n.t('msg_error', error=str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            self.i18n.t('title_about'),
            self.i18n.t('about_text', version=__version__)
        )
    
    def check_updates_silent(self):
        """Check for updates silently on startup"""
        try:
            has_update, latest, url = check_for_updates(__version__)
            if has_update:
                # Show notification in UI thread
                self.root.after(1000, lambda: self.show_update_notification(latest, url))
        except:
            pass  # Silently fail
    
    def check_updates(self):
        """Check for updates (manual)"""
        try:
            has_update, latest, url = check_for_updates(__version__)
            if has_update:
                self.show_update_notification(latest, url)
            else:
                messagebox.showinfo("Updates", self.i18n.t('update_no_updates'))
        except Exception as e:
            messagebox.showerror("Error", f"Could not check for updates: {e}")
    
    def show_update_notification(self, version, url):
        """Show update available dialog"""
        result = messagebox.askyesno(
            self.i18n.t('title_update_available'),
            self.i18n.t('update_message', version=version)
        )
        if result:
            import webbrowser
            webbrowser.open(url)


def main():
    """Main entry point for desktop app"""
    root = tk.Tk()
    app = SubtitleKitApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
