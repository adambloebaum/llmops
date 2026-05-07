# Hardware Inventory

Collected: `2026-05-07T02:07:09Z` through `2026-05-07T02:11:03Z`

Deployment root: `/home/adam`
Model storage target: `/home/adam/llm-models`

## Summary

- Hostname: `home-compute`
- OS: Ubuntu 24.04.4 LTS, kernel `6.8.0-110-generic`
- CPU: AMD Ryzen 9 5950X, 16 cores / 32 threads
- RAM: 62 GiB usable
- NUMA: 1 node
- GPU: 1x NVIDIA GeForce RTX 3080 10 GiB, Ampere
- NVIDIA driver: `580.126.09`
- CUDA exposed by driver: `13.0`
- Docker: installed and running
- NVIDIA container runtime: installed and verified with CUDA 13 container
- Tailscale IPv4: `100.114.124.62`
- Intended endpoint bind: Tailscale IP only, not public LAN

## CPU / Memory / NUMA

### `lscpu`

- Architecture: `x86_64`
- CPU: `AMD Ryzen 9 5950X 16-Core Processor`
- CPUs: `32`
- Threads per core: `2`
- Cores per socket: `16`
- Sockets: `1`
- CPU max MHz: `5084.8931`
- CPU min MHz: `2200.0000`
- NUMA nodes: `1`
- NUMA node0 CPUs: `0-31`
- Virtualization: AMD-V
- Cache: L1d 512 KiB, L1i 512 KiB, L2 8 MiB, L3 64 MiB

### `numactl --hardware`

- Available nodes: `1`
- Node 0 CPUs: `0-31`
- Node 0 size: `64223 MB`
- Node 0 free at collection: `60908 MB`
- Node distance: local distance `10`

### `free -h`

```text
               total        used        free      shared  buff/cache   available
Mem:            62Gi       1.7Gi        59Gi       2.0Mi       2.2Gi        61Gi
Swap:          8.0Gi          0B       8.0Gi
```

### `sudo dmidecode -t memory`

Result: unavailable without interactive sudo.

```text
sudo: a password is required
```

Impact: DIMM count/speed cannot be DMI-verified in this autonomous run. Usable RAM was verified from kernel/NUMA views.

## GPU / CUDA / Topology

### `nvidia-smi`

- Attached GPUs: `1`
- GPU 0: `NVIDIA GeForce RTX 3080`
- Bus ID: `00000000:07:00.0`
- Driver: `580.126.09`
- CUDA: `13.0`
- VRAM total: `10240 MiB`
- VRAM reserved by driver: `365 MiB`
- VRAM free at idle: `9875 MiB`
- Idle temp: `21 C`
- Idle power: about `7.6 W`
- Power limit: `320 W`
- Slowdown temp: `95 C`
- Shutdown temp: `98 C`
- Max operating temp: `93 C`
- ECC: N/A
- MIG: N/A
- Running compute processes: none

### PCIe from `nvidia-smi -q`

- PCIe generation max: `4`
- PCIe generation current at idle: `1`
- PCIe device max: `4`
- PCIe host max: `4`
- Link width max: `16x`
- Link width current: `16x`
- Replays since reset: `0`

Interpretation: idle downshift to Gen1 is normal power management. The link is not lane-downtrained; width is x16. Under load it should train up toward Gen4.

### `nvidia-smi topo -m`

Single GPU only:

- GPU0 CPU affinity: `0-31`
- GPU0 NUMA affinity: `0`
- GPU NUMA ID: N/A

No NVLink is present or relevant for a single RTX 3080.

## PCIe Topology

### `lspci -nn`

```text
01:00.0 Non-Volatile memory controller [0108]: Micron/Crucial Technology Device [c0a9:5427] (rev 01)
04:00.0 Non-Volatile memory controller [0108]: Samsung Electronics Co Ltd NVMe SSD Controller SM981/PM981/PM983 [144d:a808]
07:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA102 [GeForce RTX 3080 Lite Hash Rate] [10de:2216] (rev a1)
07:00.1 Audio device [0403]: NVIDIA Corporation GA102 High Definition Audio Controller [10de:1aef] (rev a1)
```

### `lspci -vvv`

Unprivileged PCIe capability reads are blocked:

```text
Capabilities: <access denied>
Kernel driver in use: nvidia
Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
```

PCIe generation and width were verified through `nvidia-smi -q`.

## Storage

### `df -hT`

```text
Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/nvme0n1p2 ext4      457G   19G  415G   5% /
/dev/nvme0n1p1 vfat      1.1G  6.2M  1.1G   1% /boot/efi
```

### `lsblk`

```text
NAME                      MODEL                   SERIAL            SIZE TYPE FSTYPE      MOUNTPOINTS         ROTA TRAN
nvme1n1                   Samsung SSD 970 EVO 1TB S5H9NS0NB82097H 931.5G disk                                    0 nvme
├─nvme1n1p1                                                           1G part vfat                               0 nvme
├─nvme1n1p2                                                           2G part ext4                               0 nvme
└─nvme1n1p3                                                       928.5G part LVM2_member                        0 nvme
  └─ubuntu--vg-ubuntu--lv                                           100G lvm  ext4                               0
nvme0n1                   CT500P310SSD8           253352231F44    465.8G disk
├─nvme0n1p1                                                           1G part vfat        /boot/efi
└─nvme0n1p2                                                       464.7G part ext4        /
```

Model storage is on `/dev/nvme0n1p2` for now because it has 415 GiB free and is mounted at `/`.

### Sequential read benchmark

Command used:

```bash
dd if=/dev/zero of=/home/adam/llm-models/.storage-readtest bs=64M count=64 oflag=direct status=progress
sync
dd if=/home/adam/llm-models/.storage-readtest of=/dev/null bs=64M iflag=direct status=progress
rm -f /home/adam/llm-models/.storage-readtest
```

Results:

- Direct write: 4.0 GiB in 0.976 s, about `4.4 GB/s`
- Direct read: 4.0 GiB in 0.605 s, about `7.1 GB/s`

Storage is not expected to bottleneck model load for the selected 7B INT4 class model.

## Network

### Interfaces

```text
lo               UNKNOWN        127.0.0.1/8 ::1/128
enp5s0           DOWN
wlan0            UP             192.168.0.29/24 ...
tailscale0       UNKNOWN        100.114.124.62/32 fd7a:115c:a1e0::1139:7c3e/128
docker0          DOWN           172.17.0.1/16
```

### MTU / speed

```text
docker0 speed=-1 mtu=1500 operstate=down
enp5s0 speed=unknown mtu=1500 operstate=down
lo speed=unknown mtu=65536 operstate=unknown
tailscale0 speed=-1 mtu=1280 operstate=unknown
wlan0 speed=unknown mtu=1500 operstate=up
```

### Tailscale

```text
100.114.124.62  home-compute  adambloebaum@  linux
100.102.195.9   adams-iphone  adambloebaum@  iOS
100.120.205.4   base          adambloebaum@  linux    offline
100.72.28.94    demo          adambloebaum@  windows  offline
```

Tailscale IPv4: `100.114.124.62`
Tailscale IPv6: `fd7a:115c:a1e0::1139:7c3e`

## Container / CUDA Runtime

### Docker

- Docker Engine: `29.4.0`
- Docker Compose plugin: `v5.1.2`
- containerd: `2.2.2`
- Cgroup driver: `systemd`
- Cgroup version: `2`
- Docker root: `/var/lib/docker`
- NVIDIA runtimes present: `nvidia`
- CDI devices discovered: `nvidia.com/gpu=0`, GPU UUID, and `nvidia.com/gpu=all`
- Running containers at collection: none

### NVIDIA container toolkit

Installed packages:

- `nvidia-container-toolkit 1.19.0-1`
- `nvidia-container-toolkit-base 1.19.0-1`
- `libnvidia-container-tools 1.19.0-1`
- `libnvidia-container1 1.19.0-1`

Runtime verification:

```text
docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
```

Result: succeeded; container saw the RTX 3080 and driver.

### Existing CUDA / Python

- `nvcc`: not installed on host
- `python3`: present
- `conda`, `micromamba`, `uv`, `pipx`: not detected in PATH
- No running inference services detected

### Listening ports before deployment

Notable pre-existing listeners:

- SSH: `0.0.0.0:22`, `[::]:22`
- Netdata-like monitoring: `0.0.0.0:19999`, `[::]:19999`
- Prometheus-like service: `*:9090`
- Tailscale service ports on `100.114.124.62` and IPv6 Tailscale address

No OpenAI-compatible inference endpoint was listening before deployment.

## Power / Thermal Budget

Assumed PSU until proven otherwise: Corsair HX1000.

Estimated sustained draw:

- RTX 3080: up to `320 W` at default power limit
- Ryzen 5950X package: roughly `105 W` stock TDP class, higher under boost
- Motherboard, NVMe, RAM, fans, USB, networking: roughly `50-100 W`
- Sustained full-system estimate: `475-575 W`
- Transient GPU spikes can exceed board power briefly; combined transient budget still appears reasonable for an HX1000 if the PSU is healthy and properly cabled.

Thermal headroom at idle is excellent: GPU `21 C`, fan `0%`, no throttle flags active. Sustained-load logging is still required during benchmarks.

## Flags

- Missing NVLink bridges: not applicable; single RTX 3080.
- Failed GPUs: none detected.
- Unstable thermals: not observed at idle; must verify under sustained inference load.
- Insufficient PCIe bandwidth: no lane downtraining detected; x16 width verified. Current Gen1 is idle power saving, max Gen4 is available.
- Questionable PSU margins: no immediate concern under HX1000 assumption, but PSU model was not physically verified.
- Primary constraint: 10 GiB VRAM. Long-context serving is KV-cache limited, so dense 7B INT4-class deployment is the correct initial target.
