import os
import subprocess
import tkinter as tk
from tkinter import messagebox

class WattNodeClient(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WattNode")

        tk.Button(self, text="Detect NVIDIA GPU", command=self.detect_gpu).pack(pady=10)
        tk.Button(self, text="Register Node", command=self.register_node).pack(pady=10)
        tk.Button(self, text="Manage Jobs", command=self.manage_jobs).pack(pady=10)

    def detect_gpu(self):
        try:
            output = subprocess.check_output(["nvidia-smi"], stderr=subprocess.STDOUT)
            messagebox.showinfo("NVIDIA GPU", output.decode())
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to detect GPU: {e.output.decode()}")

    def register_node(self):
        # Placeholder for node registration logic
        messagebox.showinfo("Register Node", "Node registered successfully.")

    def manage_jobs(self):
        # Placeholder for job management logic
        messagebox.showinfo("Manage Jobs", "Job management interface.")

def create_appimage():
    subprocess.run(["linuxdeployqt", "appdir/usr/share/applications/wattnode.desktop", "-appimage"])

def create_deb():
    os.makedirs("deb_package/DEBIAN", exist_ok=True)
    with open("deb_package/DEBIAN/control", "w") as f:
        f.write("""Package: wattnode
Version: 1.0
Section: base
Priority: optional
Architecture: amd64
Depends: python3, python3-tk
Maintainer: Your Name <youremail@example.com>
Description: WattNode Linux Client
""")
    os.makedirs("deb_package/usr/local/bin", exist_ok=True)
    shutil.copy("wattnode.py", "deb_package/usr/local/bin/")
    subprocess.run(["dpkg-deb", "--build", "deb_package"])

def build_script():
    create_appimage()
    create_deb()

if __name__ == "__main__":
    client = WattNodeClient()
    client.geometry("300x200")
    client.mainloop()