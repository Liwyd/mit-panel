// MIT Panel monitoring agent.
//
// Deliberately dependency-free: only the Go standard library, so the built
// binary is a few MB and idles at a few MB of RAM with effectively no CPU
// use between heartbeats. It only ever makes outbound HTTPS requests to the
// panel - no listening port, so it works behind NAT/firewalls untouched and
// can't be reached from outside.
//
// Configured entirely through environment variables (see the systemd unit
// written by install.sh):
//
//	PANEL_URL        Base panel URL, e.g. https://panel.example.com/dashboard
//	AGENT_TOKEN       Per-server token issued when the server was added in MIT Panel
//	INTERVAL_SECONDS  Heartbeat interval (default 10)
package main

import (
	"bytes"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type metrics struct {
	CPUPercent float64 `json:"cpu_percent"`
	CPUCores   int     `json:"cpu_cores"`
	RAMUsed    uint64  `json:"ram_used"`
	RAMTotal   uint64  `json:"ram_total"`
	SwapUsed   uint64  `json:"swap_used"`
	SwapTotal  uint64  `json:"swap_total"`
	DiskUsed   uint64  `json:"disk_used"`
	DiskTotal  uint64  `json:"disk_total"`
}

type heartbeatResponse struct {
	Reboot bool `json:"reboot"`
}

type cpuSample struct {
	idle  uint64
	total uint64
}

func readCPUSample() (cpuSample, error) {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return cpuSample{}, err
	}
	line := strings.SplitN(string(data), "\n", 2)[0]
	fields := strings.Fields(line)
	if len(fields) < 5 || fields[0] != "cpu" {
		return cpuSample{}, os.ErrInvalid
	}

	var total uint64
	var idle uint64
	for i, f := range fields[1:] {
		v, err := strconv.ParseUint(f, 10, 64)
		if err != nil {
			continue
		}
		total += v
		if i == 3 || i == 4 {
			idle += v
		}
	}
	return cpuSample{idle: idle, total: total}, nil
}

func cpuPercent(prev, curr cpuSample) float64 {
	totalDelta := curr.total - prev.total
	idleDelta := curr.idle - prev.idle
	if totalDelta == 0 {
		return 0
	}
	used := float64(totalDelta-idleDelta) / float64(totalDelta) * 100
	if used < 0 {
		return 0
	}
	if used > 100 {
		return 100
	}
	return used
}

func cpuCores() int {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0
	}
	count := 0
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "cpu") && len(line) > 3 && line[3] >= '0' && line[3] <= '9' {
			count++
		}
	}
	return count
}

func readMemory() (used, total, swapUsed, swapTotal uint64) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, 0, 0, 0
	}

	values := map[string]uint64{}
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Fields(strings.TrimSpace(parts[1]))
		if len(val) == 0 {
			continue
		}
		n, err := strconv.ParseUint(val[0], 10, 64)
		if err != nil {
			continue
		}
		values[key] = n * 1024
	}

	total = values["MemTotal"]
	available, ok := values["MemAvailable"]
	if !ok {
		available = values["MemFree"] + values["Buffers"] + values["Cached"]
	}
	if available > total {
		available = total
	}
	used = total - available

	swapTotal = values["SwapTotal"]
	swapFree := values["SwapFree"]
	if swapFree > swapTotal {
		swapFree = swapTotal
	}
	swapUsed = swapTotal - swapFree
	return
}

func readDisk(path string) (used, total uint64) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return 0, 0
	}
	total = stat.Blocks * uint64(stat.Bsize)
	free := stat.Bfree * uint64(stat.Bsize)
	if free > total {
		free = total
	}
	used = total - free
	return
}

func collect(prev cpuSample) (metrics, cpuSample) {
	curr, err := readCPUSample()
	pct := 0.0
	if err == nil {
		pct = cpuPercent(prev, curr)
	} else {
		curr = prev
	}

	ramUsed, ramTotal, swapUsed, swapTotal := readMemory()
	diskUsed, diskTotal := readDisk("/")

	return metrics{
		CPUPercent: pct,
		CPUCores:   cpuCores(),
		RAMUsed:    ramUsed,
		RAMTotal:   ramTotal,
		SwapUsed:   swapUsed,
		SwapTotal:  swapTotal,
		DiskUsed:   diskUsed,
		DiskTotal:  diskTotal,
	}, curr
}

func sendHeartbeat(client *http.Client, endpoint, token string, m metrics) (bool, error) {
	body, err := json.Marshal(m)
	if err != nil {
		return false, err
	}

	req, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return false, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Agent-Token", token)

	resp, err := client.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, nil
	}

	var parsed heartbeatResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return false, nil
	}
	return parsed.Reboot, nil
}

func reboot() {
	log.Println("reboot requested by panel, rebooting now")
	if err := exec.Command("systemctl", "reboot").Run(); err == nil {
		return
	}
	_ = exec.Command("reboot").Run()
}

func main() {
	panelURL := strings.TrimRight(os.Getenv("PANEL_URL"), "/")
	token := os.Getenv("AGENT_TOKEN")
	if panelURL == "" || token == "" {
		log.Fatal("PANEL_URL and AGENT_TOKEN must be set")
	}

	interval := 10 * time.Second
	if raw := os.Getenv("INTERVAL_SECONDS"); raw != "" {
		if secs, err := strconv.Atoi(raw); err == nil && secs > 0 {
			interval = time.Duration(secs) * time.Second
		}
	}

	endpoint := panelURL + "/agent/heartbeat"
	client := &http.Client{Timeout: 10 * time.Second}

	prev, _ := readCPUSample()
	time.Sleep(1 * time.Second)

	for {
		m, curr := collect(prev)
		prev = curr

		shouldReboot, err := sendHeartbeat(client, endpoint, token, m)
		if err != nil {
			log.Printf("heartbeat failed: %v", err)
		} else if shouldReboot {
			reboot()
		}

		time.Sleep(interval)
	}
}
