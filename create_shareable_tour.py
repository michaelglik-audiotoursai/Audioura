"""
Create a shareable tour using GitHub Pages.
"""
import os
import sys
import shutil
import subprocess
import webbrowser
import time

def create_github_repo(tour_name, html_file_path):
    """Create a GitHub repository for sharing the tour."""
    # Create a temporary directory for the repository
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.join(script_dir, f"{tour_name}_repo")
    
    # Create directory if it doesn't exist
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    os.makedirs(repo_dir)
    
    # Copy the HTML file to the repository
    html_filename = os.path.basename(html_file_path)
    shutil.copy2(html_file_path, os.path.join(repo_dir, "index.html"))
    
    # Create a README.md file
    with open(os.path.join(repo_dir, "README.md"), "w") as f:
        f.write(f"# {tour_name.replace('_', ' ').title()} Audio Tour\n\n")
        f.write("This repository contains an audio tour that works offline.\n\n")
        f.write("## How to Use\n\n")
        f.write("1. Open the tour on your phone: https://YOUR-USERNAME.github.io/" + f"{tour_name}/\n")
        f.write("2. Add to home screen when prompted\n")
        f.write("3. The tour will work offline once added to your home screen\n")
    
    # Initialize git repository
    os.chdir(repo_dir)
    
    print("\n=== GitHub Repository Setup ===")
    print("Follow these steps to share your tour:")
    
    print("\n1. Create a new repository on GitHub:")
    print(f"   - Name: {tour_name}")
    print("   - Make it Public")
    print("   - Don't add README, .gitignore, or license")
    print("\n   Go to: https://github.com/new")
    print("   Press Enter when you've created the repository...")
    input()
    
    print("\n2. Run these commands in your terminal:")
    print(f"   cd {repo_dir}")
    print("   git init")
    print("   git add .")
    print('   git commit -m "Initial commit"')
    print(f"   git branch -M main")
    username = input("\n   Enter your GitHub username: ")
    print(f"   git remote add origin https://github.com/{username}/{tour_name}.git")
    print(f"   git push -u origin main")
    
    print("\n3. Enable GitHub Pages:")
    print(f"   - Go to: https://github.com/{username}/{tour_name}/settings/pages")
    print("   - Under 'Source', select 'main' branch")
    print("   - Click 'Save'")
    print("   - Wait a few minutes for the site to be published")
    
    print("\n4. Share this link with others:")
    share_url = f"https://{username}.github.io/{tour_name}/"
    print(f"   {share_url}")
    
    print("\nWould you like to open the repository setup page?")
    if input("Enter 'y' to open: ").lower() == 'y':
        webbrowser.open("https://github.com/new")
    
    return share_url

def create_qr_code(url, output_path):
    """Create a QR code for the URL."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output_path)
        print(f"\nQR code created: {output_path}")
        print("Share this QR code with others to easily access your tour.")
        
        # Open the QR code
        webbrowser.open(f"file://{output_path}")
        
    except ImportError:
        print("\nTo create a QR code, install qrcode: pip install qrcode[pil]")

def create_netlify_drop_instructions(html_file_path):
    """Create instructions for using Netlify Drop."""
    print("\n=== Netlify Drop Instructions ===")
    print("Netlify Drop is the easiest way to share your tour:")
    
    print("\n1. Go to: https://app.netlify.com/drop")
    print("2. Drag and drop your HTML file onto the page")
    print("3. Wait for upload to complete")
    print("4. Your tour will be available at a random URL")
    print("5. You can claim the site to set a custom URL")
    
    print("\nWould you like to open Netlify Drop?")
    if input("Enter 'y' to open: ").lower() == 'y':
        webbrowser.open("https://app.netlify.com/drop")

def main():
    """Main function."""
    print("=== Audio Tour Sharing Tool ===")
    
    # Get the HTML file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_files = [f for f in os.listdir(script_dir) if f.endswith('_single_file.html')]
    
    if not html_files:
        print("No HTML tour files found. Create one first using single_file_app_builder.py")
        return
    
    print("\nAvailable tour files:")
    for i, f in enumerate(html_files, 1):
        print(f"{i}. {f}")
    
    try:
        choice = int(input("\nEnter the number of the file to share (or press Enter for the first one): ") or "1")
        if 1 <= choice <= len(html_files):
            html_file = html_files[choice-1]
        else:
            print("Invalid choice. Using the first file.")
            html_file = html_files[0]
    except ValueError:
        print("Invalid input. Using the first file.")
        html_file = html_files[0]
    
    html_file_path = os.path.join(script_dir, html_file)
    tour_name = html_file.replace('_single_file.html', '')
    
    print(f"\nSelected tour: {tour_name}")
    
    # Show sharing options
    print("\nSharing Options:")
    print("1. GitHub Pages (requires GitHub account)")
    print("2. Netlify Drop (easiest, no account required)")
    
    option = input("\nEnter your choice (1 or 2): ")
    
    if option == "1":
        # GitHub Pages
        share_url = create_github_repo(tour_name, html_file_path)
        qr_path = os.path.join(script_dir, f"{tour_name}_qr.png")
        create_qr_code(share_url, qr_path)
    else:
        # Netlify Drop
        create_netlify_drop_instructions(html_file_path)

if __name__ == "__main__":
    main()