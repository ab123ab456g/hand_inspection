import cv2
import sys

BACKENDS = []
if sys.platform.startswith("win"):
    BACKENDS = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY)]
else:
    BACKENDS = [("ANY", cv2.CAP_ANY)]

print("OpenCV:", cv2.__version__)
print("Python:", sys.version)
print("Testing camera indices 0..7")
print("Close Teams/Zoom/OBS/browser camera tabs before running.\n")

found = []
for idx in range(8):
    for name, backend in BACKENDS:
        cap = cv2.VideoCapture(idx, backend)
        opened = cap.isOpened()
        ok = False
        shape = None
        if opened:
            ok, frame = cap.read()
            if ok and frame is not None:
                shape = frame.shape
        cap.release()
        print(f"index={idx} backend={name:5} opened={opened} read={ok} shape={shape}")
        if opened and ok:
            found.append((idx, name, shape))

print("\nWorking combinations:")
if not found:
    print("NONE")
    print("\nCheck Windows Settings > Privacy & security > Camera > Camera access and Let desktop apps access your camera.")
    print("Also test the Windows Camera app. If that app cannot open the cameras, this is outside OpenCV.")
else:
    for row in found:
        print(row)
