#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════════════════════
#  WATERMARK GENIE 2.0 - PROFESSIONAL BATCH WATERMARKING TOOL
# ════════════════════════════════════════════════════════════════════════════════
#  Author: Glen E. Grant - Creative
#  Website: www.glenegrant.com
#  Email: info@glenegrant.com
#  License: MIT
#  Last Updated: 2025-07-15
# ════════════════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────────────────────────
# IMPORTS & DEPENDENCIES
# ────────────────────────────────────────────────────────────────────────────────

import csv
import json
import time
import threading
import argparse
import sys
import os
import webbrowser
import urllib.parse
import logging
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
import concurrent.futures as cf

# Core Image Processing
from PIL import Image, ImageTk, UnidentifiedImageError

# GUI Framework
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, simpledialog
from tkinter import ttk as tkttk

# Optional Enhanced UI (ttkbootstrap)
try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    BOOTSTRAP_AVAILABLE = True
except ImportError:
    import tkinter.ttk as ttk
    BOOTSTRAP_AVAILABLE = False
    SUCCESS = DANGER = SECONDARY = INFO = PRIMARY = 'default'

# Optional Drag-and-Drop Support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

# ────────────────────────────────────────────────────────────────────────────────
# APPLICATION CONSTANTS & CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────────

# Application Metadata
APP_NAME = "Watermark Genie"
VERSION = "2.0.0"
AUTHOR = "Glen E. Grant"
HELP_URL = "https://www.glenegrant.com/genie"
SUPPORT_EMAIL = "info@glenegrant.com"

# File Processing Configuration
# NOTE: AVIF and HEIC removed due to compatibility issues
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}
MAX_BATCH_SIZE = 5000
MAX_DIRECTORY_DEPTH = 50

# UI Configuration
DEFAULT_CANVAS_SIZE = (400, 280)
MAX_CANVAS_WIDTH = 450
MAX_CANVAS_HEIGHT = 400
PREVIEW_MAX_SIZE = 400

# Watermark Position Grid (9-point system)
ANCHOR_POSITIONS = {
    (0,0): "TL", (0,1): "TC", (0,2): "TR",  # Top row
    (1,0): "CL", (1,1): "CC", (1,2): "CR",  # Center row
    (2,0): "BL", (2,1): "BC", (2,2): "BR"   # Bottom row
}

# Output Format Options
FORMAT_OPTIONS = {
    'Same as source': None,
    'JPG': 'JPEG', 
    'PNG': 'PNG', 
    'WEBP': 'WEBP'
}

EXTRA_FORMAT_OPTIONS = {
    'None': None,
    'JPG': 'JPEG',
    'PNG': 'PNG', 
    'WEBP': 'WEBP'
}

# Default Application Settings
DEFAULT_SETTINGS = {
    'anchor': 'BR',          # Bottom-right placement
    'opacity': 80,           # 80% opacity
    'margin': 25,            # 25px margin from edges
    'scale': 30,             # 30% of image width
    'max_size': 1000,        # Max dimension 1000px
    'format': 'Same as source',
    'extra_format': 'None',
    'auto_scale': False,     # Scale to width (not shortest edge)
    'dry_run': False,        # Actually save files
    'create_zip': False      # Don't create ZIP by default
}

# ────────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ────────────────────────────────────────────────────────────────────────────────

def setup_logging():
    """Configure application logging for debugging and monitoring."""
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

logger = setup_logging()

# ────────────────────────────────────────────────────────────────────────────────
# CORE IMAGE PROCESSING ENGINE
# ────────────────────────────────────────────────────────────────────────────────

class ImageProcessor:
    """Handles all image processing operations including resizing and watermarking."""
    
    @staticmethod
    def resize_maintain_aspect(image, max_dimension):
        """
        Resize image while maintaining aspect ratio.
        
        Args:
            image (PIL.Image): Source image
            max_dimension (int): Maximum width or height
            
        Returns:
            PIL.Image: Resized image
        """
        width, height = image.size
        if max(width, height) <= max_dimension:
            return image.copy()
        
        if width >= height:
            new_width = max_dimension
            new_height = int(max_dimension * height / width)
        else:
            new_width = int(max_dimension * width / height)
            new_height = max_dimension
            
        return image.resize((new_width, new_height), Image.LANCZOS)
    
    @staticmethod
    def apply_watermark(base_image, watermark, position, opacity, margin, target_width):
        """
        Apply watermark to base image with specified parameters.
        
        Args:
            base_image (PIL.Image): Base image to watermark
            watermark (PIL.Image): Watermark image (PNG with transparency)
            position (str): Position code (TL, TC, TR, CL, CC, CR, BL, BC, BR)
            opacity (int): Opacity percentage (0-100)
            margin (int): Margin from edges in pixels
            target_width (int): Target watermark width in pixels
            
        Returns:
            PIL.Image: Watermarked image
        """
        # Ensure watermark has transparency channel
        if watermark.mode != 'RGBA':
            watermark = watermark.convert('RGBA')
        
        # Ensure minimum watermark size for visibility
        target_width = max(target_width, 30)
        
        # Scale watermark if needed
        if watermark.width > target_width:
            scale_factor = target_width / watermark.width
            new_size = (
                int(watermark.width * scale_factor),
                int(watermark.height * scale_factor)
            )
            watermark = watermark.resize(new_size, Image.LANCZOS)
        
        # Apply opacity if less than 100%
        if opacity < 100:
            alpha = watermark.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity / 100))
            watermark.putalpha(alpha)
        
        # Calculate position coordinates
        base_width, base_height = base_image.size
        wm_width, wm_height = watermark.size
        
        # X-axis positioning
        if 'L' in position:      # Left
            x = margin
        elif 'R' in position:    # Right
            x = base_width - wm_width - margin
        else:                    # Center
            x = (base_width - wm_width) // 2
        
        # Y-axis positioning
        if 'T' in position:      # Top
            y = margin
        elif 'B' in position:    # Bottom
            y = base_height - wm_height - margin
        else:                    # Center
            y = (base_height - wm_height) // 2
        
        # Apply watermark to copy of base image
        result = base_image.copy()
        result.paste(watermark, (x, y), watermark)
        return result
    
    @staticmethod
    def save_image(image, output_path, format_type, exif_data=None):
        """
        Save image in specified format with optional EXIF data preservation.
        
        Args:
            image (PIL.Image): Image to save
            output_path (Path): Output file path (without extension)
            format_type (str): Format ('JPEG', 'PNG', 'WEBP')
            exif_data: Original EXIF data to preserve
        """
        if format_type == 'JPEG':
            # Convert to RGB for JPEG (no transparency support)
            rgb_image = image.convert('RGB')
            save_path = output_path.with_suffix('.jpg')
            rgb_image.save(save_path, 'JPEG', quality=95, optimize=True, exif=exif_data)
        elif format_type == 'WEBP':
            save_path = output_path.with_suffix('.webp')
            image.save(save_path, 'WEBP', quality=90, method=6)
        else:  # PNG or fallback
            save_path = output_path.with_suffix('.png')
            image.save(save_path, 'PNG', optimize=True)

# ────────────────────────────────────────────────────────────────────────────────
# FILE MANAGEMENT SYSTEM
# ────────────────────────────────────────────────────────────────────────────────

class FileManager:
    """Handles file discovery, validation, logging, and archiving operations."""
    
    @staticmethod
    def find_supported_images(directory, max_depth=MAX_DIRECTORY_DEPTH, include_subfolders=True):
        """
        Find all supported image files in directory.
        
        Args:
            directory (Path): Directory to search
            max_depth (int): Maximum subdirectory depth
            include_subfolders (bool): Whether to search recursively
            
        Returns:
            tuple: (list of image paths, count of ignored files)
        """
        if not directory.is_dir():
            return [], 0
        
        images = []
        ignored_count = 0
        
        try:
            if include_subfolders:
                # Recursive search with depth limit
                for file_path in directory.rglob('*'):
                    if (len(file_path.parts) - len(directory.parts) <= max_depth and 
                        file_path.is_file()):
                        
                        if file_path.suffix.lower() in SUPPORTED_FORMATS:
                            # Verify file can be opened
                            try:
                                with Image.open(file_path) as test_img:
                                    pass
                                images.append(file_path)
                            except Exception:
                                ignored_count += 1
                        elif file_path.suffix.lower() in {'.avif', '.heic', '.gif', '.tga', '.pcx'}:
                            ignored_count += 1  # Known unsupported formats
                        
                    if len(images) >= MAX_BATCH_SIZE:
                        logger.warning(f"Reached maximum batch size of {MAX_BATCH_SIZE} files")
                        break
            else:
                # Current directory only
                for file_path in directory.iterdir():
                    if file_path.is_file():
                        if file_path.suffix.lower() in SUPPORTED_FORMATS:
                            try:
                                with Image.open(file_path) as test_img:
                                    pass
                                images.append(file_path)
                            except Exception:
                                ignored_count += 1
                        elif file_path.suffix.lower() in {'.avif', '.heic', '.gif', '.tga', '.pcx'}:
                            ignored_count += 1
                        
                    if len(images) >= MAX_BATCH_SIZE:
                        logger.warning(f"Reached maximum batch size of {MAX_BATCH_SIZE} files")
                        break
                    
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
            
        return images, ignored_count
    
    @staticmethod
    def validate_paths(input_dir, output_dir, watermark_file):
        """
        Validate that all required paths exist and are valid.
        
        Args:
            input_dir (Path): Input directory
            output_dir (Path): Output directory
            watermark_file (Path): Watermark PNG file
            
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        if not input_dir.is_dir():
            return False, "Input directory does not exist"
        
        if not watermark_file.is_file():
            return False, "Watermark file does not exist"
        
        if watermark_file.suffix.lower() != '.png':
            return False, "Watermark must be a PNG file"
        
        # Prevent output inside input (would cause infinite recursion)
        try:
            output_dir.relative_to(input_dir)
            return False, "Output directory cannot be inside input directory"
        except ValueError:
            pass
        
        return True, "Paths are valid"
    
    @staticmethod
    def create_csv_log(output_dir, processed_files):
        """
        Create CSV log of all processed files with results.
        
        Args:
            output_dir (Path): Output directory for log file
            processed_files (list): List of processing result dictionaries
        """
        log_file = output_dir / 'watermark_processing_log.csv'
        
        try:
            with open(log_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['timestamp', 'source_file', 'output_file', 'status', 'error']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(processed_files)
                
            logger.info(f"Processing log saved to {log_file}")
        except Exception as e:
            logger.error(f"Failed to create CSV log: {e}")
    
    @staticmethod
    def create_zip_archive(source_dir, zip_name=None):
        """
        Create ZIP archive of processed files.
        
        Args:
            source_dir (Path): Directory to archive
            zip_name (str, optional): Custom archive name
            
        Returns:
            Path or None: Path to created archive, or None if failed
        """
        if not source_dir.is_dir():
            return None
        
        try:
            if not zip_name:
                timestamp = datetime.now().strftime("%Y-%m-%d_%I-%M%p")
                zip_name = f"watermarked_batch_{timestamp}.zip"
            
            zip_path = source_dir / zip_name
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                for file_path in source_dir.rglob('*'):
                    if file_path.is_file():
                        arc_path = file_path.relative_to(source_dir)
                        zipf.write(file_path, arc_path)
            
            logger.info(f"ZIP archive created: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Failed to create ZIP archive: {e}")
            return None

# ────────────────────────────────────────────────────────────────────────────────
# SETTINGS & PRESET MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────────

class SettingsManager:
    """Manages application settings and user presets."""
    
    def __init__(self, app_dir):
        """
        Initialize settings manager.
        
        Args:
            app_dir (Path): Application data directory
        """
        self.app_dir = app_dir
        self.presets_dir = app_dir / 'presets'
        self.settings_file = app_dir / 'settings.json'
        self.presets_dir.mkdir(parents=True, exist_ok=True)
    
    def save_preset(self, name, settings):
        """
        Save current settings as a named preset.
        
        Args:
            name (str): Preset name
            settings (dict): Settings dictionary
            
        Returns:
            bool: Success status
        """
        try:
            preset_file = self.presets_dir / f"{name}.wgpreset"
            preset_data = {
                'name': name,
                'created': datetime.now().isoformat(),
                'version': VERSION,
                'settings': settings
            }
            
            with open(preset_file, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, indent=2)
            
            logger.info(f"Preset '{name}' saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save preset '{name}': {e}")
            return False
    
    def load_preset(self, preset_file):
        """
        Load settings from preset file.
        
        Args:
            preset_file (Path): Path to preset file
            
        Returns:
            dict or None: Settings dictionary or None if failed
        """
        try:
            with open(preset_file, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
            
            return preset_data.get('settings', {})
            
        except Exception as e:
            logger.error(f"Failed to load preset {preset_file}: {e}")
            return None
    
    def get_available_presets(self):
        """Get list of available preset files."""
        return list(self.presets_dir.glob('*.wgpreset'))

# ────────────────────────────────────────────────────────────────────────────────
# MAIN GUI APPLICATION CLASS
# ────────────────────────────────────────────────────────────────────────────────

class WatermarkGenieGUI:
    """Main GUI application class for Watermark Genie."""
    
    def __init__(self):
        """Initialize the GUI application."""
        # ═══ ROOT WINDOW SETUP ═══
        if DND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.resizable(False, False)
        
        # ═══ COMPONENT INITIALIZATION ═══
        self.settings_manager = SettingsManager(Path.home() / '.watermark-genie')
        self.image_processor = ImageProcessor()
        self.file_manager = FileManager()
        
        # ═══ UI SETUP ═══
        self._setup_theme()
        self._setup_icon()
        self._setup_variables()
        
        # ═══ STATE VARIABLES ═══
        self.stop_event = threading.Event()
        self.preview_image = None
        self.processing_thread = None
        self.preview_images = []
        self.current_preview_index = 0
        self.overwrite_mode = 'ask'
        self.ignored_files_count = 0
        self.preview_update_pending = False  # Prevents rapid-fire preview updates
        
        # ═══ BUILD INTERFACE ═══
        self._build_interface()
        self._update_file_count()
        
        logger.info(f"{APP_NAME} {VERSION} initialized successfully")
    
    # ────────────────────────────────────────────────────────────────────────────
    # UI SETUP & INITIALIZATION
    # ────────────────────────────────────────────────────────────────────────────
    
    def _setup_theme(self):
        """Configure application theme and styling."""
        if BOOTSTRAP_AVAILABLE:
            try:
                self.style = ttk.Style(theme="flatly")
                self.current_theme = "flatly"
            except Exception as e:
                logger.warning(f"Failed to apply bootstrap theme: {e}")
                self.style = ttk.Style()
                self.current_theme = "default"
        else:
            self.style = ttk.Style()
            self.current_theme = "default"
    
    def _setup_icon(self):
        """Load and set application icon."""
        self.icon_image = None
        
        for icon_name in ["icon.ico", "icon.png"]:
            icon_path = Path(__file__).parent / icon_name
            if icon_path.is_file():
                try:
                    if icon_name.endswith('.ico'):
                        self.root.iconbitmap(str(icon_path))
                    else:
                        img = Image.open(icon_path).resize((64, 64), Image.LANCZOS)
                        self.icon_image = ImageTk.PhotoImage(img)
                        self.root.iconphoto(False, self.icon_image)
                    logger.info(f"Icon loaded: {icon_name}")
                    break
                except Exception as e:
                    logger.warning(f"Could not load icon {icon_name}: {e}")
    
    def _setup_variables(self):
        """Initialize all Tkinter variables for UI controls."""
        # String variables for paths and selections
        string_vars = ['input_dir', 'output_dir', 'watermark_file', 'anchor', 'format', 'extra_format']
        self.vars = {name: tk.StringVar() for name in string_vars}
        
        # Integer variables for numeric settings
        int_vars = ['opacity', 'margin', 'scale', 'max_size']
        self.vars.update({name: tk.IntVar() for name in int_vars})
        
        # Boolean variables for checkboxes
        bool_vars = ['auto_scale', 'dry_run', 'dark_theme', 'create_zip', 'include_subfolders']
        self.vars.update({name: tk.BooleanVar() for name in bool_vars})
        
        # Set default values
        self.vars['anchor'].set(DEFAULT_SETTINGS['anchor'])
        self.vars['format'].set(DEFAULT_SETTINGS['format'])
        self.vars['extra_format'].set(DEFAULT_SETTINGS['extra_format'])
        self.vars['opacity'].set(DEFAULT_SETTINGS['opacity'])
        self.vars['margin'].set(DEFAULT_SETTINGS['margin'])
        self.vars['scale'].set(DEFAULT_SETTINGS['scale'])
        self.vars['max_size'].set(DEFAULT_SETTINGS['max_size'])
        self.vars['auto_scale'].set(DEFAULT_SETTINGS['auto_scale'])
        self.vars['dry_run'].set(DEFAULT_SETTINGS['dry_run'])
        self.vars['create_zip'].set(DEFAULT_SETTINGS['create_zip'])
        self.vars['include_subfolders'].set(True)
        
        # Set up variable change callbacks
        self.vars['input_dir'].trace_add('write', lambda *_: self._update_file_count())
        self.vars['include_subfolders'].trace_add('write', lambda *_: self._update_file_count())
        
        # ═══ LIVE PREVIEW UPDATES ═══
        # Update preview when any watermark setting changes
        preview_update_vars = ['watermark_file', 'anchor', 'opacity', 'margin', 'scale', 'auto_scale']
        for var_name in preview_update_vars:
            if var_name in self.vars:
                self.vars[var_name].trace_add('write', lambda *_: self._delayed_preview_update())
    
    # ────────────────────────────────────────────────────────────────────────────
    # UI CONSTRUCTION METHODS
    # ────────────────────────────────────────────────────────────────────────────
    
    def _build_interface(self):
        """Build the complete user interface."""
        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.grid(row=0, column=0, sticky='nsew')
        
        # Build interface sections in order
        self._build_header_section(main_frame)
        self._build_path_section(main_frame) 
        self._build_main_content(main_frame)
        self._build_controls_section(main_frame)
        self._build_status_section(main_frame)
        self._build_footer_section(main_frame)
    
    def _build_header_section(self, parent):
        """Build application header with title and icon."""
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        
        # Application icon (if available)
        if self.icon_image:
            try:
                small_icon = self.icon_image.subsample(2, 2)
                icon_label = ttk.Label(header_frame, image=small_icon)
                icon_label.image = small_icon
                icon_label.pack(side=tk.LEFT, padx=(0, 10))
            except:
                pass
        
        # Title and subtitle
        title_frame = ttk.Frame(header_frame)
        title_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(title_frame, text=f"{APP_NAME} {VERSION}", 
                               font=('Segoe UI', 14, 'bold'))
        title_label.pack(anchor='w')
        
        subtitle_label = ttk.Label(title_frame, text="Professional Batch Watermarking Tool",
                                  font=('Segoe UI', 9))
        subtitle_label.pack(anchor='w')
    
    def _build_path_section(self, parent):
        """Build file path selection section."""
        paths_frame = ttk.LabelFrame(parent, text="File Paths", padding=10)
        paths_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        
        # Path input rows
        self._create_path_row(paths_frame, "Input Directory:", 'input_dir', 0, is_directory=True)
        self._create_path_row(paths_frame, "Output Directory:", 'output_dir', 1, is_directory=True)
        self._create_path_row(paths_frame, "Watermark (PNG):", 'watermark_file', 2, is_directory=False)
        
        # File count and options info panel
        info_frame = ttk.Frame(paths_frame)
        info_frame.grid(row=0, column=3, rowspan=3, padx=(20, 0), sticky='n')
        
        self.file_count_label = ttk.Label(info_frame, text="Files: 0", font=('Segoe UI', 9, 'bold'))
        if BOOTSTRAP_AVAILABLE:
            self.file_count_label.configure(bootstyle=INFO)
        self.file_count_label.pack(anchor='w')
        
        self.ignored_count_label = ttk.Label(info_frame, text="", font=('Segoe UI', 8), foreground='gray')
        self.ignored_count_label.pack(anchor='w')
        
        ttk.Checkbutton(info_frame, text="Include subfolders", 
                       variable=self.vars['include_subfolders'],
                       command=self._update_file_count).pack(anchor='w', pady=(5, 0))
        
        self.processing_info = ttk.Label(info_frame, text="Select input folder", 
                                        font=('Segoe UI', 8), foreground='gray')
        self.processing_info.pack(anchor='w', pady=(2, 0))
    
    def _create_path_row(self, parent, label, var_name, row, is_directory):
        """Create a file/directory selection row."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 10))
        
        path_entry = ttk.Entry(parent, textvariable=self.vars[var_name], width=50)
        path_entry.grid(row=row, column=1, sticky='ew', padx=(0, 5))
        
        browse_btn = ttk.Button(parent, text="Browse...", width=10,
                               command=lambda: self._browse_path(var_name, is_directory))
        browse_btn.grid(row=row, column=2, sticky='w')
        
        parent.columnconfigure(1, weight=1)
    
    def _build_main_content(self, parent):
        """Build main content area with options and preview."""
        content_frame = ttk.Frame(parent)
        content_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        
        self._build_options_section(content_frame)
        self._build_preview_section(content_frame)
    
    def _build_options_section(self, parent):
        """Build watermark options configuration panel."""
        options_frame = ttk.LabelFrame(parent, text="Watermark Options", padding=10)
        options_frame.grid(row=0, column=0, sticky='new', padx=(0, 5))
        
        # Position selection grid
        position_frame = ttk.LabelFrame(options_frame, text="Position", padding=5)
        position_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        self._build_position_grid(position_frame)
        
        # Numeric options (opacity, margin, size, max size)
        options_data = [
            ("Opacity %:", 'opacity', 0, 100),
            ("Margin (px):", 'margin', 0, 200),  
            ("Size %:", 'scale', 1, 100),
            ("Max Size (px):", 'max_size', 100, 5000)
        ]
        
        for i, (label, var_name, min_val, max_val) in enumerate(options_data):
            row = i + 1
            ttk.Label(options_frame, text=label).grid(row=row, column=0, sticky='w', pady=2)
            
            entry = ttk.Entry(options_frame, textvariable=self.vars[var_name], width=8)
            entry.grid(row=row, column=1, sticky='w', padx=(10, 0), pady=2)
        
        # Format selection
        format_frame = ttk.Frame(options_frame)
        format_frame.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        
        ttk.Label(format_frame, text="Format:").grid(row=0, column=0, sticky='w')
        format_combo = ttk.Combobox(format_frame, textvariable=self.vars['format'],
                                   values=list(FORMAT_OPTIONS.keys()), state='readonly', width=15)
        format_combo.grid(row=0, column=1, sticky='w', padx=(10, 0))
        
        ttk.Label(format_frame, text="Extra:").grid(row=1, column=0, sticky='w', pady=(5, 0))
        extra_combo = ttk.Combobox(format_frame, textvariable=self.vars['extra_format'],
                                  values=list(EXTRA_FORMAT_OPTIONS.keys()), state='readonly', width=15)
        extra_combo.grid(row=1, column=1, sticky='w', padx=(10, 0), pady=(5, 0))
        
        # Processing options checkboxes
        checkbox_frame = ttk.Frame(options_frame)
        checkbox_frame.grid(row=6, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        
        ttk.Checkbutton(checkbox_frame, text="Auto-scale to shortest edge", 
                       variable=self.vars['auto_scale']).pack(anchor='w')
        
        ttk.Checkbutton(checkbox_frame, text="Dry run (preview only)", 
                       variable=self.vars['dry_run']).pack(anchor='w', pady=(5, 0))
        
        ttk.Checkbutton(checkbox_frame, text="Create ZIP archive after processing", 
                       variable=self.vars['create_zip']).pack(anchor='w', pady=(5, 0))
    
    def _build_position_grid(self, parent):
        """Build 9-point watermark position selection grid."""
        for row in range(3):
            for col in range(3):
                frame = ttk.Frame(parent, width=30, height=30, relief='ridge', borderwidth=1)
                frame.grid(row=row, column=col, padx=2, pady=2)
                frame.grid_propagate(False)
                
                position_value = ANCHOR_POSITIONS[(row, col)]
                radio = ttk.Radiobutton(frame, variable=self.vars['anchor'], value=position_value)
                radio.pack(expand=True, fill='both')
    
    def _build_preview_section(self, parent):
        """Build live preview panel with navigation and drag-drop."""
        preview_frame = ttk.LabelFrame(parent, text="Preview", padding=5)
        preview_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        # Navigation controls
        nav_frame = ttk.Frame(preview_frame)
        nav_frame.pack(fill='x', pady=(0, 5))
        
        self.prev_btn = ttk.Button(nav_frame, text="◀", width=3, command=self._prev_preview)
        self.prev_btn.pack(side=tk.LEFT)
        
        self.preview_info = ttk.Label(nav_frame, text="No images", font=('Segoe UI', 8))
        self.preview_info.pack(side=tk.LEFT, expand=True)
        
        self.next_btn = ttk.Button(nav_frame, text="▶", width=3, command=self._next_preview)
        self.next_btn.pack(side=tk.RIGHT)
        
        # Preview canvas with dynamic sizing
        self.preview_canvas = tk.Canvas(preview_frame, width=DEFAULT_CANVAS_SIZE[0], 
                                       height=DEFAULT_CANVAS_SIZE[1], bg='white', 
                                       relief='sunken', borderwidth=1)
        self.preview_canvas.pack()
        
        # Enable drag-and-drop if available
        if DND_AVAILABLE:
            try:
                self.preview_canvas.drop_target_register(DND_FILES)
                self.preview_canvas.dnd_bind('<<Drop>>', self._handle_drop)
            except Exception as e:
                logger.warning(f"Could not enable drag-and-drop: {e}")
        
        # Preview controls
        btn_frame = ttk.Frame(preview_frame)
        btn_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Button(btn_frame, text="Update Preview", 
                  command=self._update_preview).pack(side=tk.LEFT, padx=(0, 5))
        
        # File conflict handling options
        overwrite_frame = ttk.LabelFrame(preview_frame, text="File Conflicts", padding=5)
        overwrite_frame.pack(fill='x', pady=(5, 0))
        
        self.overwrite_var = tk.StringVar(value='ask')
        ttk.Radiobutton(overwrite_frame, text="Ask each time", variable=self.overwrite_var, 
                       value='ask').pack(anchor='w')
        ttk.Radiobutton(overwrite_frame, text="Overwrite existing", variable=self.overwrite_var, 
                       value='overwrite').pack(anchor='w')
        ttk.Radiobutton(overwrite_frame, text="Skip existing", variable=self.overwrite_var, 
                       value='skip').pack(anchor='w')
    
    def _build_controls_section(self, parent):
        """Build main control buttons section."""
        controls_frame = ttk.Frame(parent)
        controls_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        
        # Primary action buttons
        self.start_button = ttk.Button(controls_frame, text="Start Processing", 
                                      command=self.start_processing)
        if BOOTSTRAP_AVAILABLE:
            self.start_button.configure(bootstyle=SUCCESS)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.cancel_button = ttk.Button(controls_frame, text="Cancel", 
                                       command=self.cancel_processing, state='disabled')
        if BOOTSTRAP_AVAILABLE:
            self.cancel_button.configure(bootstyle=DANGER)
        self.cancel_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Utility buttons
        ttk.Button(controls_frame, text="Clear All", 
                  command=self.clear_all_fields).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(controls_frame, text="Save Preset", 
                  command=self.save_preset).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(controls_frame, text="Load Preset", 
                  command=self.load_preset).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(controls_frame, text="Toggle Theme", 
                  command=self.toggle_theme).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(controls_frame, text="Help", 
                  command=self.show_help).pack(side=tk.LEFT)
    
    def _build_status_section(self, parent):
        """Build status display section with progress bar."""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        
        self.progress_bar = ttk.Progressbar(status_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.pack()
    
    def _build_footer_section(self, parent):
        """Build application footer with copyright."""
        footer_frame = ttk.Frame(parent)
        footer_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        copyright_label = ttk.Label(footer_frame, text=f"© 2025 {AUTHOR}",
                                   font=('Segoe UI', 8, 'italic'))
        copyright_label.pack()
    
    # ────────────────────────────────────────────────────────────────────────────
    # FILE HANDLING & UI INTERACTIONS
    # ────────────────────────────────────────────────────────────────────────────
    
    def _browse_path(self, var_name, is_directory):
        """Handle file/directory browsing."""
        if is_directory:
            path = filedialog.askdirectory(title=f"Select {var_name.replace('_', ' ').title()}")
        else:
            path = filedialog.askopenfilename(
                title="Select Watermark PNG File",
                filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
            )
        
        if path:
            self.vars[var_name].set(path)
            if var_name in ['input_dir', 'watermark_file']:
                self._update_preview()
    
    def _handle_drop(self, event):
        """Handle drag-and-drop file operations."""
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                file_path = Path(files[0])
                
                if file_path.is_dir():
                    self.vars['input_dir'].set(str(file_path))
                elif file_path.suffix.lower() == '.png':
                    self.vars['watermark_file'].set(str(file_path))
                
                self._update_preview()
                
        except Exception as e:
            logger.error(f"Error handling drop: {e}")
    
    def _update_file_count(self):
        """Update file count display based on current input directory."""
        input_dir = self.vars['input_dir'].get()
        if input_dir:
            try:
                directory = Path(input_dir)
                include_subfolders = self.vars['include_subfolders'].get()
                files, ignored_count = self.file_manager.find_supported_images(directory, include_subfolders=include_subfolders)
                count = len(files)
                self.ignored_files_count = ignored_count
                
                if include_subfolders:
                    main_folder_files, main_ignored = self.file_manager.find_supported_images(directory, include_subfolders=False)
                    subfolder_files = count - len(main_folder_files)
                    
                    self.file_count_label.configure(text=f"Files: {count:,}")
                    if ignored_count > 0:
                        self.ignored_count_label.configure(text=f"Ignored: {ignored_count}")
                    else:
                        self.ignored_count_label.configure(text="")
                    
                    if subfolder_files > 0:
                        self.processing_info.configure(text=f"{len(main_folder_files)} main + {subfolder_files} in subfolders")
                    else:
                        self.processing_info.configure(text="Main folder only")
                else:
                    self.file_count_label.configure(text=f"Files: {count:,}")
                    if ignored_count > 0:
                        self.ignored_count_label.configure(text=f"Ignored: {ignored_count}")
                    else:
                        self.ignored_count_label.configure(text="")
                    self.processing_info.configure(text="Main folder only")
                    
            except Exception as e:
                logger.error(f"Error counting files: {e}")
                self.file_count_label.configure(text="Files: Error")
                self.ignored_count_label.configure(text="")
                self.processing_info.configure(text="Error scanning")
        else:
            self.file_count_label.configure(text="Files: 0")
            self.ignored_count_label.configure(text="")
            self.processing_info.configure(text="Select input folder")
    
    # ────────────────────────────────────────────────────────────────────────────
    # PREVIEW SYSTEM (FIXED FOR PORTRAIT IMAGES)
    # ────────────────────────────────────────────────────────────────────────────
    
    def _update_preview(self):
        """
        Generate preview image selection.
        Finds mix of landscape and portrait images for comprehensive preview.
        """
        try:
            input_dir = self.vars['input_dir'].get()
            watermark_file = self.vars['watermark_file'].get()
            
            if not input_dir or not watermark_file:
                self._clear_preview("Select input folder and watermark")
                return
            
            directory = Path(input_dir)
            wm_path = Path(watermark_file)
            
            if not directory.is_dir():
                self._clear_preview("Invalid input directory")
                return
                
            if not wm_path.is_file() or wm_path.suffix.lower() != '.png':
                self._clear_preview("Invalid watermark file")
                return
            
            include_subfolders = self.vars['include_subfolders'].get()
            images, _ = self.file_manager.find_supported_images(directory, include_subfolders=include_subfolders)
            
            if not images:
                self._clear_preview("No supported images found")
                return
            
            # Categorize images by orientation for balanced preview
            portrait_images = []
            landscape_images = []
            
            for img_path in images[:12]:  # Check first 12 images for variety
                try:
                    with Image.open(img_path) as img:
                        if img.height > img.width:
                            portrait_images.append(img_path)
                        else:
                            landscape_images.append(img_path)
                        
                        # Stop when we have enough of each type
                        if len(portrait_images) >= 3 and len(landscape_images) >= 3:
                            break
                except Exception:
                    continue
            
            # Select balanced mix for preview
            selected_images = []
            selected_images.extend(landscape_images[:3])
            selected_images.extend(portrait_images[:3])
            
            # Fill remaining slots if needed
            if len(selected_images) < 6:
                remaining_images = [img for img in images[:12] if img not in selected_images]
                selected_images.extend(remaining_images[:6 - len(selected_images)])
            
            if not selected_images:
                selected_images = images[:6]
            
            self.preview_images = selected_images
            self.current_preview_index = 0
            
            logger.info(f"Preview images selected: {len(self.preview_images)} images "
                       f"({len(landscape_images)} landscape, {len(portrait_images)} portrait)")
            
            self._update_single_preview()
            
        except Exception as e:
            logger.error(f"Error updating preview: {e}")
            self._clear_preview("Preview error")
    
    def _update_single_preview(self):
        """
        ═══ PORTRAIT WATERMARK FIX ═══
        Generate single watermarked preview image.
        Fixed calculation ensures portraits get properly sized watermarks.
        """
        if not self.preview_images:
            self._clear_preview("No images available")
            return
        
        try:
            watermark_file = self.vars['watermark_file'].get()
            if not watermark_file or not Path(watermark_file).exists():
                self._clear_preview("No watermark selected")
                return
            
            current_image_path = self.preview_images[self.current_preview_index]
            
            # Load base image and watermark
            try:
                base_img = Image.open(current_image_path)
                watermark_img = Image.open(watermark_file)
            except Exception as e:
                self._clear_preview(f"Error loading: {current_image_path.name}")
                return
            
            # Ensure watermark has transparency
            if watermark_img.mode != 'RGBA':
                watermark_img = watermark_img.convert('RGBA')
            
            # Resize base image for preview
            original_size = base_img.size
            base_img = self.image_processor.resize_maintain_aspect(base_img, PREVIEW_MAX_SIZE)
            
            # Get current settings
            try:
                opacity = int(self.vars['opacity'].get())
                margin = int(self.vars['margin'].get())
                scale = int(self.vars['scale'].get())
                anchor = str(self.vars['anchor'].get())
                auto_scale = bool(self.vars['auto_scale'].get())
            except:
                # Fallback to defaults if settings invalid
                opacity, margin, scale, anchor, auto_scale = 80, 25, 30, "BR", False
            
            base_width, base_height = base_img.size
            is_portrait = base_height > base_width
            
            # ═══ CRITICAL FIX: Portrait watermark sizing ═══
            if auto_scale:
                if is_portrait:
                    # For portraits in auto-scale mode: use 50% of width
                    target_width = max(40, int(base_width * 0.5))
                else:
                    # For landscapes in auto-scale mode: use shortest edge
                    target_width = max(40, int(min(base_width, base_height) * scale / 100))
            else:
                if is_portrait:
                    # For portraits in normal mode: apply 1.5x multiplier
                    target_width = max(40, int(base_width * scale / 100 * 1.5))
                else:
                    # For landscapes in normal mode: use width-based calculation
                    target_width = max(40, int(base_width * scale / 100))
            
            orientation = "Portrait" if is_portrait else "Landscape"
            logger.info(f"Preview: {orientation} {base_width}x{base_height}, watermark: {target_width}px")
            
            # Apply watermark using fixed calculation
            try:
                preview_img = self.image_processor.apply_watermark(
                    base_img, watermark_img, anchor, opacity, margin, target_width
                )
            except Exception as e:
                logger.error(f"Watermark application failed: {e}")
                preview_img = base_img  # Show unwatermarked image on error
            
            # Display in canvas with dynamic sizing
            try:
                self.preview_image = ImageTk.PhotoImage(preview_img)
                
                # ═══ DYNAMIC CANVAS SIZING FIX ═══
                # Resize canvas to fit the actual image
                img_width, img_height = preview_img.size
                
                # Ensure canvas isn't too large for the UI
                canvas_width = min(img_width + 20, MAX_CANVAS_WIDTH)  # +20 for padding
                canvas_height = min(img_height + 20, MAX_CANVAS_HEIGHT)  # +20 for padding
                
                # Update canvas size to fit the image
                self.preview_canvas.configure(width=canvas_width, height=canvas_height)
                
                # Clear and center the image in the canvas
                self.preview_canvas.delete('all')
                self.preview_canvas.create_image(
                    canvas_width // 2, canvas_height // 2, 
                    image=self.preview_image
                )
                
                # Update preview info with orientation indication
                img_name = current_image_path.name
                if len(img_name) > 20:
                    img_name = img_name[:17] + "..."
                
                # Show canvas dimensions for debugging
                orientation_info = f"{orientation} ({img_width}×{img_height})"
                
                self.preview_info.configure(
                    text=f"{self.current_preview_index + 1}/{len(self.preview_images)} - {orientation_info} - {img_name}"
                )
                
                # Update navigation buttons
                self.prev_btn.configure(state='normal' if self.current_preview_index > 0 else 'disabled')
                self.next_btn.configure(state='normal' if self.current_preview_index < len(self.preview_images) - 1 else 'disabled')
                
            except Exception as e:
                logger.error(f"Failed to display preview: {e}")
                self._clear_preview("Display error")
        
        except Exception as e:
            logger.error(f"Unexpected preview error: {e}")
            self._clear_preview("Unexpected error")
    
    def _clear_preview(self, message=""):
        """Clear preview canvas and show message."""
        # Reset canvas to default size
        self.preview_canvas.configure(width=DEFAULT_CANVAS_SIZE[0], height=DEFAULT_CANVAS_SIZE[1])
        self.preview_canvas.delete('all')
        
        if message:
            self.preview_canvas.create_text(
                DEFAULT_CANVAS_SIZE[0] // 2, DEFAULT_CANVAS_SIZE[1] // 2,
                text=message, fill="gray", font=('Segoe UI', 10)
            )
        self.preview_info.configure(text="No images")
        self.prev_btn.configure(state='disabled')
        self.next_btn.configure(state='disabled')
    
    def _prev_preview(self):
        """Navigate to previous preview image."""
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self._update_single_preview()
    
    def _next_preview(self):
        """Navigate to next preview image."""
        if self.current_preview_index < len(self.preview_images) - 1:
            self.current_preview_index += 1
            self._update_single_preview()
    
    def _delayed_preview_update(self):
        """
        Delayed preview update to prevent rapid-fire updates during UI interaction.
        Uses 500ms delay to batch multiple setting changes together.
        """
        if self.preview_update_pending:
            return
        
        self.preview_update_pending = True
        
        def do_update():
            if self.preview_images:  # Only update if we have images loaded
                self._update_single_preview()
            self.preview_update_pending = False
        
        # Schedule update after 500ms delay
        self.root.after(500, do_update)
    
    # ────────────────────────────────────────────────────────────────────────────
    # BATCH PROCESSING ENGINE
    # ────────────────────────────────────────────────────────────────────────────
    
    def start_processing(self):
        """
        Start batch processing workflow.
        Validates inputs, confirms with user, then starts processing thread.
        """
        # Validate required paths
        input_dir = Path(self.vars['input_dir'].get())
        output_dir = Path(self.vars['output_dir'].get())
        watermark_file = Path(self.vars['watermark_file'].get())
        
        is_valid, error_msg = self.file_manager.validate_paths(input_dir, output_dir, watermark_file)
        if not is_valid:
            messagebox.showerror("Validation Error", error_msg)
            return
        
        # Find files to process
        include_subfolders = self.vars['include_subfolders'].get()
        files_to_process, ignored = self.file_manager.find_supported_images(input_dir, include_subfolders=include_subfolders)
        if not files_to_process:
            messagebox.showerror("No Files", "No supported image files found in input directory.")
            return
        
        # Check batch size limit
        if len(files_to_process) > MAX_BATCH_SIZE:
            messagebox.showerror("Batch Too Large", 
                               f"Found {len(files_to_process)} files. Maximum batch size is {MAX_BATCH_SIZE}.")
            return
        
        # Build confirmation message
        subfolder_text = " (including subfolders)" if include_subfolders else " (main folder only)"
        dry_run_text = " (DRY RUN - no files will be saved)" if self.vars['dry_run'].get() else ""
        zip_text = " → ZIP archive will be created" if self.vars['create_zip'].get() and not self.vars['dry_run'].get() else ""
        ignored_text = f" ({ignored} files ignored)" if ignored > 0 else ""
        confirm_msg = f"Process {len(files_to_process)} files{subfolder_text}?{ignored_text}{dry_run_text}{zip_text}"
        
        if not messagebox.askyesno("Confirm Processing", confirm_msg):
            return
        
        # Prepare for processing
        output_dir.mkdir(parents=True, exist_ok=True)
        self.stop_event.clear()
        
        # Update UI state
        self.start_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.progress_bar.configure(maximum=len(files_to_process), value=0)
        self.status_var.set("Processing...")
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._process_images,
            args=(files_to_process, input_dir, output_dir, watermark_file),
            daemon=True
        )
        self.processing_thread.start()
        
        logger.info(f"Started processing {len(files_to_process)} files")
    
    def _process_images(self, files, input_dir, output_dir, watermark_file):
        """
        Main image processing worker function.
        Runs in separate thread to avoid blocking UI.
        """
        try:
            # Load watermark once for all processing
            watermark = Image.open(watermark_file).convert('RGBA')
            
            # Get current settings
            settings = self._get_current_settings()
            settings['overwrite_mode'] = self.overwrite_var.get()
            extra_format = EXTRA_FORMAT_OPTIONS.get(settings['extra_format'])
            main_format = FORMAT_OPTIONS.get(settings['format'])
            
            results = []
            processed_count = 0
            
            def process_single_file(file_path):
                """Process individual file with watermark application."""
                try:
                    # Load and prepare image
                    image = Image.open(file_path)
                    exif_data = image.info.get('exif')
                    
                    # Resize if needed
                    if image.width > settings['max_size'] or image.height > settings['max_size']:
                        image = self.image_processor.resize_maintain_aspect(image, settings['max_size'])
                    
                    # ═══ SAME PORTRAIT FIX APPLIED TO BATCH PROCESSING ═══
                    is_portrait = image.height > image.width
                    
                    if settings['auto_scale']:
                        if is_portrait:
                            target_width = max(40, int(image.width * 0.5))
                        else:
                            target_width = max(40, int(min(image.size) * settings['scale'] / 100))
                    else:
                        if is_portrait:
                            target_width = max(40, int(image.width * settings['scale'] / 100 * 1.5))
                        else:
                            target_width = max(40, int(image.width * settings['scale'] / 100))
                    
                    # Apply watermark
                    watermarked = self.image_processor.apply_watermark(
                        image, watermark, settings['anchor'], 
                        settings['opacity'], settings['margin'], target_width
                    )
                    
                    # Determine output path
                    relative_path = file_path.relative_to(input_dir)
                    output_path = output_dir / relative_path.with_suffix('')
                    
                    # Save files if not dry run
                    saved_files = []
                    if not settings['dry_run']:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        should_process = True
                        if self._check_file_exists(output_path, main_format, extra_format):
                            if settings.get('overwrite_mode', 'ask') == 'skip':
                                should_process = False
                        
                        if should_process:
                            # Save main format
                            if main_format:
                                self.image_processor.save_image(watermarked, output_path, main_format, exif_data)
                                saved_files.append(f"{output_path}.{main_format.lower()}")
                            else:
                                # Use original format
                                original_format = file_path.suffix.upper()[1:]
                                if original_format == 'JPG':
                                    original_format = 'JPEG'
                                self.image_processor.save_image(watermarked, output_path, original_format, exif_data)
                                saved_files.append(str(output_path.with_suffix(file_path.suffix)))
                            
                            # Save extra format if specified
                            if extra_format and extra_format != main_format:
                                self.image_processor.save_image(watermarked, output_path, extra_format, exif_data)
                                saved_files.append(f"{output_path}.{extra_format.lower()}")
                        else:
                            saved_files.append("SKIPPED - File exists")
                    
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'source_file': str(file_path),
                        'output_file': '; '.join(saved_files) if saved_files else 'DRY RUN',
                        'status': 'SUCCESS',
                        'error': ''
                    }
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Failed to process {file_path}: {error_msg}")
                    return {
                        'timestamp': datetime.now().isoformat(),
                        'source_file': str(file_path),
                        'output_file': '',
                        'status': 'ERROR',
                        'error': error_msg
                    }
            
            # Multi-threaded processing for performance
            max_workers = min(os.cpu_count() or 4, 8)
            with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {executor.submit(process_single_file, file): file for file in files}
                
                for future in cf.as_completed(future_to_file):
                    if self.stop_event.is_set():
                        logger.info("Processing cancelled by user")
                        break
                    
                    result = future.result()
                    results.append(result)
                    processed_count += 1
                    
                    # Update UI progress (thread-safe)
                    self.root.after(0, lambda: self.progress_bar.configure(value=processed_count))
                    self.root.after(0, lambda: self.status_var.set(f"Processed {processed_count}/{len(files)}"))
            
            # Create processing log
            if not settings['dry_run'] and results:
                self.file_manager.create_csv_log(output_dir, results)
            
            # Create ZIP archive if requested
            zip_path = None
            if settings['create_zip'] and not settings['dry_run'] and results:
                self.root.after(0, lambda: self.status_var.set("Creating ZIP archive..."))
                zip_path = self.file_manager.create_zip_archive(output_dir)
            
            # Update final status
            if self.stop_event.is_set():
                final_status = "Processing cancelled"
            else:
                success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
                zip_info = f" (ZIP: {zip_path.name})" if zip_path else ""
                final_status = f"Complete: {success_count}/{len(files)} files processed{zip_info}"
            
            self.root.after(0, lambda: self.status_var.set(final_status))
            
        except Exception as e:
            error_msg = f"Processing error: {e}"
            logger.error(error_msg)
            self.root.after(0, lambda: self.status_var.set(error_msg))
        
        finally:
            # Reset UI state (thread-safe)
            self.root.after(0, lambda: self.start_button.configure(state='normal'))
            self.root.after(0, lambda: self.cancel_button.configure(state='disabled'))
    
    def _check_file_exists(self, output_path, main_format, extra_format):
        """Check if output file(s) already exist."""
        if main_format:
            if (output_path.parent / f"{output_path.name}.{main_format.lower()}").exists():
                return True
        else:
            # Check common extensions for original format preservation
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                if (output_path.parent / f"{output_path.name}{ext}").exists():
                    return True
        
        # Check extra format
        if extra_format and (output_path.parent / f"{output_path.name}.{extra_format.lower()}").exists():
            return True
        
        return False
    
    def cancel_processing(self):
        """Cancel ongoing processing operation."""
        self.stop_event.set()
        self.status_var.set("Cancelling...")
        logger.info("Processing cancellation requested")
    
    def _get_current_settings(self):
        """Get current settings as dictionary."""
        return {
            'anchor': self.vars['anchor'].get(),
            'opacity': self.vars['opacity'].get(),
            'margin': self.vars['margin'].get(),
            'scale': self.vars['scale'].get(),
            'max_size': self.vars['max_size'].get(),
            'format': self.vars['format'].get(),
            'extra_format': self.vars['extra_format'].get(),
            'auto_scale': self.vars['auto_scale'].get(),
            'dry_run': self.vars['dry_run'].get(),
            'create_zip': self.vars['create_zip'].get()
        }
    
    # ────────────────────────────────────────────────────────────────────────────
    # UTILITY FUNCTIONS & SETTINGS MANAGEMENT
    # ────────────────────────────────────────────────────────────────────────────
    
    def clear_all_fields(self):
        """Clear all input fields and reset to defaults."""
        path_vars = ['input_dir', 'output_dir', 'watermark_file']
        for var_name in path_vars:
            self.vars[var_name].set('')
        
        for key, value in DEFAULT_SETTINGS.items():
            if key in self.vars:
                self.vars[key].set(value)
        
        self.preview_canvas.delete('all')
        self.status_var.set("Fields cleared")
        logger.info("All fields cleared")
    
    def save_preset(self):
        """Save current settings as a named preset."""
        preset_name = simpledialog.askstring("Save Preset", "Enter preset name:")
        if preset_name:
            settings = self._get_current_settings()
            if self.settings_manager.save_preset(preset_name, settings):
                messagebox.showinfo("Success", f"Preset '{preset_name}' saved successfully!")
            else:
                messagebox.showerror("Error", "Failed to save preset.")
    
    def load_preset(self):
        """Load settings from a preset file."""
        preset_file = filedialog.askopenfilename(
            title="Load Preset",
            initialdir=self.settings_manager.presets_dir,
            filetypes=[("Watermark Genie Presets", "*.wgpreset"), ("All files", "*.*")]
        )
        
        if preset_file:
            settings = self.settings_manager.load_preset(Path(preset_file))
            if settings:
                self._apply_settings(settings)
                self.status_var.set("Preset loaded successfully")
                messagebox.showinfo("Success", "Preset loaded successfully!")
            else:
                messagebox.showerror("Error", "Failed to load preset.")
    
    def _apply_settings(self, settings):
        """Apply loaded settings to UI controls."""
        for key, value in settings.items():
            if key in self.vars:
                self.vars[key].set(value)
        
        self._update_preview()
    
    def toggle_theme(self):
        """Toggle between light and dark themes."""
        if BOOTSTRAP_AVAILABLE:
            try:
                current_dark = self.vars['dark_theme'].get()
                new_theme = "darkly" if not current_dark else "flatly"
                self.style.theme_use(new_theme)
                self.vars['dark_theme'].set(not current_dark)
                self.current_theme = new_theme
                logger.info(f"Theme changed to {new_theme}")
            except Exception as e:
                logger.error(f"Failed to toggle theme: {e}")
    
    def show_help(self):
        """Display comprehensive help and about dialog."""
        help_window = Toplevel(self.root)
        help_window.title("About Watermark Genie")
        help_window.resizable(False, False)
        help_window.geometry("500x600")
        help_window.geometry(f"+{self.root.winfo_rootx()+50}+{self.root.winfo_rooty()+50}")
        
        help_window.configure(padx=20, pady=20)
        
        # Scrollable content area
        canvas = tk.Canvas(help_window)
        scrollbar = ttk.Scrollbar(help_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Application icon
        if self.icon_image:
            try:
                small_icon = self.icon_image.subsample(2, 2)
                icon_label = ttk.Label(scrollable_frame, image=small_icon)
                icon_label.image = small_icon
                icon_label.pack(pady=(0, 10))
            except:
                pass
        
        # Title and subtitle
        ttk.Label(scrollable_frame, text=f"{APP_NAME} {VERSION}", 
                 font=('Segoe UI', 16, 'bold')).pack()
        
        ttk.Label(scrollable_frame, text="Professional Batch Watermarking Tool - for Creators",
                 font=('Segoe UI', 10, 'italic')).pack(pady=(5, 15))
        
        # Developer info with clickable website
        dev_frame = ttk.Frame(scrollable_frame)
        dev_frame.pack(pady=(0, 5))
        
        ttk.Label(dev_frame, text="Developed by Glen E. Grant - ",
                 font=('Segoe UI', 11, 'bold')).pack(side=tk.LEFT)
        
        website_label = ttk.Label(dev_frame, text="www.glenegrant.com", cursor='hand2',
                                 font=('Segoe UI', 11, 'bold', 'underline'))
        if BOOTSTRAP_AVAILABLE:
            website_label.configure(bootstyle=INFO)
        website_label.pack(side=tk.LEFT)
        website_label.bind('<Button-1>', 
                          lambda e: webbrowser.open("https://www.glenegrant.com"))
        
        # Support contact section
        contact_frame = ttk.LabelFrame(scrollable_frame, text="Support & Contact", padding=10)
        contact_frame.pack(fill='x', pady=(10, 15))
        
        ttk.Label(contact_frame, text="For comments, bug reports and suggestions:",
                 font=('Segoe UI', 9)).pack()
        
        contact_label = ttk.Label(contact_frame, text=SUPPORT_EMAIL, cursor='hand2',
                                 font=('Segoe UI', 9, 'underline'))
        if BOOTSTRAP_AVAILABLE:
            contact_label.configure(bootstyle=INFO)
        contact_label.pack(pady=(5, 0))
        contact_label.bind('<Button-1>', 
                          lambda e: webbrowser.open(f"mailto:{SUPPORT_EMAIL}?subject=Watermark%20Genie%20Support"))
        
        # Download section
        download_frame = ttk.LabelFrame(scrollable_frame, text="Latest Version", padding=10)
        download_frame.pack(fill='x', pady=(0, 15))
        
        ttk.Label(download_frame, text="Download the latest version:",
                 font=('Segoe UI', 9)).pack()
        
        github_label = ttk.Label(download_frame, text="github.com/Glenskii/watermark-gienie", 
                               cursor='hand2', font=('Segoe UI', 9, 'underline'))
        if BOOTSTRAP_AVAILABLE:
            github_label.configure(bootstyle=INFO)
        github_label.pack(pady=(5, 0))
        github_label.bind('<Button-1>', 
                         lambda e: webbrowser.open("https://github.com/Glenskii/watermark-gienie"))
        
        # Features list
        features_frame = ttk.LabelFrame(scrollable_frame, text="Key Features", padding=10)
        features_frame.pack(fill='x', pady=(0, 15))
        
        features = [
            "• Batch watermarking with drag-and-drop support",
            "• Live preview with 9-point positioning grid", 
            "• Multi-core processing for faster performance",
            "• Preset manager for saving/loading configurations",
            "• Multiple output formats (JPG, PNG, WEBP)",
            "• Command-line interface for automation",
            "• ZIP archive creation for easy distribution",
            "• EXIF data preservation",
            "• Portrait image watermark optimization"
        ]
        
        for feature in features:
            ttk.Label(features_frame, text=feature, font=('Segoe UI', 8)).pack(anchor='w')
        
        # Legal notice
        legal_frame = ttk.LabelFrame(scrollable_frame, text="Legal Notice", padding=10)
        legal_frame.pack(fill='x', pady=(0, 15))
        
        legal_text = """This computer program is protected by copyright laws and international treaties. 
Unauthorized reproduction or distribution of this program, or any portion of it, may result 
in severe civil and criminal penalties, and will be prosecuted to the maximum extent 
possible under Canadian law."""
        
        ttk.Label(legal_frame, text=legal_text, font=('Segoe UI', 8), 
                 wraplength=440, justify='left').pack()
        
        # License information
        license_frame = ttk.LabelFrame(scrollable_frame, text="License", padding=10)
        license_frame.pack(fill='x', pady=(0, 15))
        
        ttk.Label(license_frame, text="Released under the MIT License", 
                 font=('Segoe UI', 9, 'bold')).pack()
        ttk.Label(license_frame, text="Free for personal and commercial use", 
                 font=('Segoe UI', 8)).pack()
        
        # Copyright
        ttk.Label(scrollable_frame, text="© 2025 Glen E. Grant",
                 font=('Segoe UI', 10, 'bold')).pack(pady=(15, 10))
        
        # Action buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(pady=(10, 0))
        
        ttk.Button(button_frame, text="Documentation", 
                  command=lambda: webbrowser.open(HELP_URL)).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Close", 
                  command=help_window.destroy).pack(side=tk.LEFT)
        
        # Pack scrollable components
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def run(self):
        """Start the application main loop."""
        logger.info("Starting application main loop")
        self.root.mainloop()

# ────────────────────────────────────────────────────────────────────────────────
# COMMAND-LINE INTERFACE (CLI)
# ────────────────────────────────────────────────────────────────────────────────

class WatermarkGenieCLI:
    """Command-line interface for batch processing without GUI."""
    
    def __init__(self):
        """Initialize CLI components."""
        self.image_processor = ImageProcessor()
        self.file_manager = FileManager()
    
    def run(self, args):
        """
        Execute CLI batch processing workflow.
        
        Args:
            args: Parsed command-line arguments
        """
        # Validate paths
        input_dir = Path(args.input)
        output_dir = Path(args.output) 
        watermark_file = Path(args.watermark)
        
        is_valid, error_msg = self.file_manager.validate_paths(input_dir, output_dir, watermark_file)
        if not is_valid:
            print(f"Error: {error_msg}")
            sys.exit(1)
        
        # Find files to process
        files, ignored = self.file_manager.find_supported_images(input_dir)
        if not files:
            print("Error: No supported image files found.")
            sys.exit(1)
        
        print(f"Found {len(files)} files to process")
        if ignored > 0:
            print(f"Ignored {ignored} unsupported files")
        
        # Prepare processing
        output_dir.mkdir(parents=True, exist_ok=True)
        watermark = Image.open(watermark_file).convert('RGBA')
        
        results = []
        for i, file_path in enumerate(files, 1):
            try:
                print(f"Processing {i}/{len(files)}: {file_path.name}")
                
                # Load and prepare image
                image = Image.open(file_path)
                exif_data = image.info.get('exif')
                
                # Resize if needed
                if image.width > args.size or image.height > args.size:
                    image = self.image_processor.resize_maintain_aspect(image, args.size)
                
                # ═══ SAME PORTRAIT FIX APPLIED TO CLI ═══
                is_portrait = image.height > image.width
                
                if args.auto:
                    if is_portrait:
                        target_width = max(40, int(image.width * 0.5))
                    else:
                        target_width = max(40, int(min(image.size) * args.scale / 100))
                else:
                    if is_portrait:
                        target_width = max(40, int(image.width * args.scale / 100 * 1.5))
                    else:
                        target_width = max(40, int(image.width * args.scale / 100))
                
                # Apply watermark
                watermarked = self.image_processor.apply_watermark(
                    image, watermark, args.anchor, args.opacity, args.margin, target_width
                )
                
                # Save processed image
                relative_path = file_path.relative_to(input_dir)
                output_path = output_dir / relative_path.with_suffix('')
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                if not args.dry:
                    main_format = FORMAT_OPTIONS.get(args.fmt)
                    if main_format:
                        self.image_processor.save_image(watermarked, output_path, main_format, exif_data)
                    else:
                        # Use original format
                        original_format = file_path.suffix.upper()[1:]
                        if original_format == 'JPG':
                            original_format = 'JPEG'
                        self.image_processor.save_image(watermarked, output_path, original_format, exif_data)
                    
                    # Save extra format if specified
                    extra_format = EXTRA_FORMAT_OPTIONS.get(args.extra)
                    if extra_format and extra_format != main_format:
                        self.image_processor.save_image(watermarked, output_path, extra_format, exif_data)
                
                results.append({
                    'timestamp': datetime.now().isoformat(),
                    'source_file': str(file_path),
                    'output_file': str(output_path) if not args.dry else 'DRY RUN',
                    'status': 'SUCCESS',
                    'error': ''
                })
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                results.append({
                    'timestamp': datetime.now().isoformat(),
                    'source_file': str(file_path),
                    'output_file': '',
                    'status': 'ERROR', 
                    'error': str(e)
                })
        
        # Create processing log
        if not args.dry and results:
            self.file_manager.create_csv_log(output_dir, results)
        
        # Create ZIP archive if requested
        if args.zip and not args.dry and results:
            print("Creating ZIP archive...")
            zip_path = self.file_manager.create_zip_archive(output_dir)
            if zip_path:
                print(f"ZIP archive created: {zip_path}")
        
        # Final summary
        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
        print(f"Processing complete: {success_count}/{len(files)} files processed successfully")

# ────────────────────────────────────────────────────────────────────────────────
# COMMAND-LINE ARGUMENT PARSER SETUP
# ────────────────────────────────────────────────────────────────────────────────

def setup_cli_parser():
    """Configure command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Watermark Genie - Professional batch watermarking tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s --cli -i photos/ -o watermarked/ -w logo.png
  %(prog)s --cli -i photos/ -o watermarked/ -w logo.png --anchor BR --scale 25 --auto
  %(prog)s --cli -i photos/ -o watermarked/ -w logo.png --fmt JPG --extra WEBP --zip --dry

For more information, visit: {HELP_URL}
        """
    )
    
    # Core CLI mode flag
    parser.add_argument('--cli', action='store_true', help='Run in CLI mode')
    
    # Required paths
    parser.add_argument('-i', '--input', required=True, help='Input directory containing images')
    parser.add_argument('-o', '--output', required=True, help='Output directory for watermarked images')
    parser.add_argument('-w', '--watermark', required=True, help='Watermark PNG file')
    
    # Watermark positioning and appearance
    parser.add_argument('--anchor', choices=list(ANCHOR_POSITIONS.values()), 
                       default='BR', help='Watermark position (default: BR)')
    parser.add_argument('--opacity', type=int, default=80, 
                       help='Watermark opacity 0-100 (default: 80)')
    parser.add_argument('--margin', type=int, default=25, 
                       help='Margin from edges in pixels (default: 25)')
    parser.add_argument('--scale', type=int, default=30, 
                       help='Watermark size as percentage (default: 30)')
    parser.add_argument('--size', type=int, default=1000, 
                       help='Maximum image dimension in pixels (default: 1000)')
    
    # Output format options
    parser.add_argument('--fmt', choices=list(FORMAT_OPTIONS.keys()), 
                       default='Same as source', help='Output format (default: Same as source)')
    parser.add_argument('--extra', choices=list(EXTRA_FORMAT_OPTIONS.keys()), 
                       default='None', help='Additional output format (default: None)')
    
    # Processing options
    parser.add_argument('--auto', action='store_true', 
                       help='Scale watermark to shortest edge instead of width')
    parser.add_argument('--dry', action='store_true', 
                       help='Dry run - process but do not save files')
    parser.add_argument('--zip', action='store_true', 
                       help='Create ZIP archive of output directory after processing')
    
    return parser

# ────────────────────────────────────────────────────────────────────────────────
# APPLICATION ENTRY POINT
# ────────────────────────────────────────────────────────────────────────────────

def main():
    """Main application entry point - handles both GUI and CLI modes."""
    parser = setup_cli_parser()
    
    if '--cli' in sys.argv:
        # Command-line interface mode
        args = parser.parse_args()
        cli = WatermarkGenieCLI()
        cli.run(args)
    else:
        # Graphical user interface mode
        try:
            app = WatermarkGenieGUI()
            app.run()
        except Exception as e:
            logger.error(f"Application error: {e}")
            messagebox.showerror("Application Error", f"An unexpected error occurred:\n\n{e}")
            sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════════
# PROGRAM EXECUTION
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()