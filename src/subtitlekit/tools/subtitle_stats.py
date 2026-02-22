import pysrt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import os
import tempfile

@dataclass
class SubtitleData:
    """Stores data for a subtitle file"""
    filename: str
    raw_content: bytes
    dataframe: pd.DataFrame
    stats: Dict
    color: str = "#3498db"

    @property
    def total_lines(self) -> int:
        return len(self.dataframe)

    @property
    def avg_cps(self) -> float:
        return self.dataframe['CPS'].mean()

    @property
    def problematic_lines(self) -> int:
        return len(self.dataframe[self.dataframe['CPS'] > 20])


class SubtitleStorage:
    """Storage for multiple subtitle files"""

    COLORS = [
        "#e74c3c", "#3498db", "#2ecc71", "#9b59b6",
        "#f39c12", "#1abc9c", "#e91e63", "#00bcd4",
    ]

    def __init__(self):
        self.files: Dict[str, SubtitleData] = {}
        self._color_index = 0

    def add(self, filename: str, content: bytes, df: pd.DataFrame, stats: Dict):
        color = self.COLORS[self._color_index % len(self.COLORS)]
        self._color_index += 1
        self.files[filename] = SubtitleData(
            filename=filename,
            raw_content=content,
            dataframe=df,
            stats=stats,
            color=color
        )

    def remove(self, filename: str):
        if filename in self.files:
            del self.files[filename]

    def get(self, filename: str) -> Optional[SubtitleData]:
        return self.files.get(filename)

    def list_files(self) -> List[str]:
        return list(self.files.keys())

    def clear(self):
        self.files.clear()
        self._color_index = 0

    def __len__(self) -> int:
        return len(self.files)


def calculate_duration(subtitle_item) -> float:
    start = subtitle_item.start.ordinal / 1000.0
    end = subtitle_item.end.ordinal / 1000.0
    return end - start

def calculate_cps(text: str, duration: float) -> float:
    if duration == 0:
        return 0
    return len(text) / duration

def calculate_gap(current_sub, next_sub) -> float:
    if next_sub is None:
        return float('inf')
    current_end = current_sub.end.ordinal / 1000.0
    next_start = next_sub.start.ordinal / 1000.0
    return next_start - current_end

def calculate_ideal_cps(text: str, current_duration: float, gap_to_next: float, max_duration: float=7.0, target_cps: float=20.0):
    chars = len(text)
    current_cps = chars / current_duration if current_duration > 0 else 0

    if current_cps <= target_cps:
        return current_cps, current_duration

    ideal_duration = chars / target_cps
    max_extension = max(0.0, min(gap_to_next, max_duration - current_duration))
    max_possible_duration = current_duration + max_extension

    final_duration = max(current_duration, min(ideal_duration, max_possible_duration))
    ideal_cps = chars / final_duration if final_duration > 0 else current_cps

    return ideal_cps, final_duration

def analyze_subtitles_from_bytes(content: bytes, filename: str) -> Tuple[pd.DataFrame, Dict]:
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1253', 'iso-8859-7']
    subs = None

    for encoding in encodings:
        try:
            text = content.decode(encoding)
            temp_path = None
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
                f.write(text)
                temp_path = f.name
            try:
                subs = pysrt.open(temp_path, encoding='utf-8')
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
            break
        except Exception:
            continue

    if subs is None:
        raise ValueError(f"Could not read {filename}")

    data = []
    for i, sub in enumerate(subs):
        text = sub.text.replace('\n', ' ')
        duration = calculate_duration(sub)
        chars = len(text)
        cps = calculate_cps(text, duration)
        
        next_sub = subs[i + 1] if i + 1 < len(subs) else None
        gap = calculate_gap(sub, next_sub)
        ideal_cps, ideal_duration = calculate_ideal_cps(text, duration, gap)
        
        start_time = f"{sub.start.hours:02d}:{sub.start.minutes:02d}:{sub.start.seconds:02d}"

        data.append({
            'Item': i + 1,
            'Start': start_time,
            'Text': text[:50] + '...' if len(text) > 50 else text,
            'Full_Text': text,
            'Characters': chars,
            'Duration': round(duration, 2),
            'CPS': round(cps, 2),
            'Gap_to_Next': round(gap, 2) if gap != float('inf') else None,
            'Ideal_Duration': round(ideal_duration, 2),
            'Ideal_CPS': round(ideal_cps, 2),
            'Needs_Adjustment': cps > 20
        })

    df = pd.DataFrame(data)
    stats = {}
    if len(df) > 0:
        stats = {
            'total_lines': len(df),
            'total_chars': df['Characters'].sum(),
            'total_duration': df['Duration'].sum(),
            'avg_cps': df['CPS'].mean(),
            'std_cps': df['CPS'].std(),
            'min_cps': df['CPS'].min(),
            'max_cps': df['CPS'].max(),
            'median_cps': df['CPS'].median(),
            'avg_ideal_cps': df['Ideal_CPS'].mean(),
            'problematic_count': len(df[df['CPS'] > 20]),
            'problematic_percent': len(df[df['CPS'] > 20]) / len(df) * 100
        }
    return df, stats

def create_single_file_chart(sub_data: SubtitleData, t: Dict[str, str] = None) -> plt.Figure:
    if t is None: t = {}
    df = sub_data.dataframe

    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    title = t.get('chart_single_title', 'Analysis: ') + sub_data.filename
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # 1. Histogram CPS
    axes[0, 0].hist(df['CPS'], bins=30, alpha=0.7, color=sub_data.color, edgecolor='black')
    axes[0, 0].axvline(20, color='red', linestyle='--', linewidth=2, label='Limit (20 CPS)')
    axes[0, 0].axvline(df['CPS'].mean(), color='green', linestyle='-', linewidth=2, label=f"Avg ({df['CPS'].mean():.1f})")
    axes[0, 0].set_xlabel('CPS', fontsize=12)
    axes[0, 0].set_ylabel(t.get('chart_freq', 'Frequency'), fontsize=12)
    axes[0, 0].set_title(t.get('chart_cps_dist', 'CPS Distribution'), fontsize=14, fontweight='bold')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)

    # 2. CPS over time
    axes[0, 1].fill_between(df['Item'], df['CPS'], alpha=0.3, color=sub_data.color)
    axes[0, 1].plot(df['Item'], df['CPS'], color=sub_data.color, linewidth=1)
    axes[0, 1].axhline(20, color='red', linestyle='--', linewidth=2, label='Limit (20 CPS)')
    axes[0, 1].set_xlabel(t.get('chart_line_num', 'Line Number'), fontsize=12)
    axes[0, 1].set_ylabel('CPS', fontsize=12)
    axes[0, 1].set_title(t.get('chart_cps_per_line', 'CPS per Line'), fontsize=14, fontweight='bold')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)

    # 3. Current vs Ideal CPS
    x = np.arange(min(20, len(df)))
    width = 0.35
    axes[1, 0].bar(x - width/2, df['CPS'].head(20), width, label=t.get('chart_current', 'Current'), color='red', alpha=0.7)
    axes[1, 0].bar(x + width/2, df['Ideal_CPS'].head(20), width, label=t.get('chart_ideal', 'Ideal'), color='green', alpha=0.7)
    axes[1, 0].axhline(20, color='blue', linestyle='--', linewidth=2)
    axes[1, 0].set_xlabel(t.get('chart_line', 'Line'), fontsize=12)
    axes[1, 0].set_ylabel('CPS', fontsize=12)
    axes[1, 0].set_title(t.get('chart_current_vs_ideal', 'Current vs Ideal CPS (first 20)'), fontsize=14, fontweight='bold')
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)

    # 4. Pie chart
    problematic = len(df[df['CPS'] > 20])
    ok = len(df) - problematic
    axes[1, 1].pie([ok, problematic], labels=['OK', 'CPS > 20'],
                   colors=['#2ecc71', '#e74c3c'], autopct='%1.1f%%', startangle=90,
                   explode=(0, 0.1))
    axes[1, 1].set_title(t.get('chart_prob_percent', 'Problematic Lines Percent'), fontsize=14, fontweight='bold')

    plt.tight_layout()
    return fig

def create_comparison_chart(data_list: List[SubtitleData], t: Dict[str, str] = None) -> plt.Figure:
    if t is None: t = {}
    
    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, axes = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(t.get('chart_comp_title', 'Subtitles Comparison'), fontsize=18, fontweight='bold')

    # 1. Overlapping CPS Distribution
    for sub_data in data_list:
        axes[0, 0].hist(sub_data.dataframe['CPS'], bins=30, alpha=0.5,
                       color=sub_data.color, label=sub_data.filename[:30], edgecolor='black')
    axes[0, 0].axvline(20, color='black', linestyle='--', linewidth=2, label='Limit (20 CPS)')
    axes[0, 0].set_xlabel('CPS', fontsize=12)
    axes[0, 0].set_ylabel(t.get('chart_freq', 'Frequency'), fontsize=12)
    axes[0, 0].set_title(t.get('chart_cps_dist_comp', 'CPS Distribution Comparison'), fontsize=14, fontweight='bold')
    axes[0, 0].legend(loc='upper right', fontsize=8)
    axes[0, 0].grid(True, alpha=0.3)

    # 2. CPS over time comparison
    for sub_data in data_list:
        df = sub_data.dataframe
        if len(df) > 0:
            x_normalized = np.linspace(0, 100, len(df))
            axes[0, 1].plot(x_normalized, df['CPS'], color=sub_data.color,
                           label=sub_data.filename[:30], alpha=0.7, linewidth=1.5)
    axes[0, 1].axhline(20, color='black', linestyle='--', linewidth=2)
    axes[0, 1].set_xlabel(t.get('chart_pos_pct', 'Position in file (%)'), fontsize=12)
    axes[0, 1].set_ylabel('CPS', fontsize=12)
    axes[0, 1].set_title(t.get('chart_cps_time_comp', 'CPS over time comparison'), fontsize=14, fontweight='bold')
    axes[0, 1].legend(loc='upper right', fontsize=8)
    axes[0, 1].grid(True, alpha=0.3)

    # 3. Box plot comparison
    valid_data = [sd for sd in data_list if len(sd.dataframe) > 0]
    if valid_data:
        box_data = [sd.dataframe['CPS'] for sd in valid_data]
        box_labels = [sd.filename[:20] for sd in valid_data]
        bp = axes[1, 0].boxplot(box_data, labels=box_labels, patch_artist=True)
        for patch, sub_data in zip(bp['boxes'], valid_data):
            patch.set_facecolor(sub_data.color)
            patch.set_alpha(0.7)
        axes[1, 0].axhline(20, color='red', linestyle='--', linewidth=2, label='Limit')
        axes[1, 0].set_ylabel('CPS', fontsize=12)
        axes[1, 0].set_title(t.get('chart_box_comp', 'CPS Box Plot Comparison'), fontsize=14, fontweight='bold')
        axes[1, 0].tick_params(axis='x', rotation=45)
        axes[1, 0].grid(True, alpha=0.3)

    # 4. Bar chart - Statistics comparison
    if valid_data:
        x = np.arange(len(valid_data))
        width = 0.2
        avg_cps = [sd.stats['avg_cps'] for sd in valid_data]
        max_cps = [sd.stats['max_cps'] for sd in valid_data]
        problematic = [sd.stats['problematic_percent'] for sd in valid_data]

        axes[1, 1].bar(x - width, avg_cps, width, label=t.get('chart_bar_avg', 'Avg CPS'), color='#3498db')
        axes[1, 1].bar(x, [p/5 for p in problematic], width, label='% Prob/5', color='#e74c3c')
        axes[1, 1].bar(x + width, [m/2 for m in max_cps], width, label='Max CPS/2', color='#2ecc71')

        axes[1, 1].set_ylabel(t.get('chart_val', 'Value'), fontsize=12)
        axes[1, 1].set_title(t.get('chart_stat_comp', 'Statistics Comparison'), fontsize=14, fontweight='bold')
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels([sd.filename[:15] for sd in valid_data], rotation=45)
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)

    plt.tight_layout()
    return fig
