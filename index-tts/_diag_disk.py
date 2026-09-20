import time, os

def read_test(path, mb=200):
    if not os.path.exists(path):
        print(f"  跳过（不存在）: {path}")
        return
    t = time.perf_counter(); read = 0
    with open(path, "rb", buffering=0) as f:
        while read < mb * 1024 * 1024:
            c = f.read(4 * 1024 * 1024)
            if not c:
                break
            read += len(c)
    el = time.perf_counter() - t
    print(f"  {path}")
    print(f"    {read/1e6:.0f}MB / {el:.2f}s -> {read/1e6/el:.1f} MB/s")

_here = os.path.dirname(os.path.abspath(__file__))
_ckpt = os.path.join(_here, "checkpoints", "IndexTTS-2")
print("=== 模型所在盘 ===")
read_test(os.path.join(_ckpt, "gpt.pth"))
read_test(os.path.join(_ckpt, "s2mel.pth"))

print("=== D 盘（对比基准） ===")
for cand in [r"D:\xm\ComfyUI\models", r"D:\xm"]:
    if os.path.isdir(cand):
        for root, _, files in os.walk(cand):
            big = [os.path.join(root, f) for f in files if os.path.getsize(os.path.join(root, f)) > 300 * 1024 * 1024]
            if big:
                read_test(big[0])
                break
        else:
            continue
        break
