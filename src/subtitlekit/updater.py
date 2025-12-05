"""
Version checking and auto-update functionality
"""
import requests
from packaging import version as pkg_version
from subtitlekit import __version__


def check_for_updates(current_version=None, repo="angelospk/subtitlekit"):
    """
    Check GitHub releases for newer versions.
    
    Args:
        current_version: Current installed version (defaults to package version)
        repo: GitHub repository in format "owner/repo"
        
    Returns:
        tuple: (update_available: bool, latest_version: str, download_url: str)
    """
    if current_version is None:
        current_version = __version__
    
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        release_data = response.json()
        latest_version = release_data['tag_name'].lstrip('v')
        
        # Compare versions
        is_newer = pkg_version.parse(latest_version) > pkg_version.parse(current_version)
        
        # Get download URL for assets (if any)
        download_url = release_data.get('html_url', '')
        
        return is_newer, latest_version, download_url
        
    except Exception as e:
        # Silently fail - don't interrupt user workflow
        return False, current_version, ""


def get_update_message(latest_version, download_url):
    """Generate user-friendly update message"""
    return f"""
╔════════════════════════════════════════╗
║   🎉 New Version Available: v{latest_version}   ║
╚════════════════════════════════════════╝

Upgrade with:
    pip install --upgrade subtitlekit

More info: {download_url}
"""


if __name__ == "__main__":
    # Test update checker
    has_update, latest, url = check_for_updates()
    if has_update:
        print(get_update_message(latest, url))
    else:
        print("✅ You're running the latest version!")
