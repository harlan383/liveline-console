package main

import "testing"

func TestParseDefaultRoute(t *testing.T) {
	info := parseDefaultRoute("default via 64.90.13.254 dev ens17 proto dhcp src 64.90.13.19 metric 100\n")
	if info.Interface != "ens17" {
		t.Fatalf("interface = %q, want ens17", info.Interface)
	}
	if info.Gateway != "64.90.13.254" {
		t.Fatalf("gateway = %q, want 64.90.13.254", info.Gateway)
	}
}

func TestLocalIPv4ForInterface(t *testing.T) {
	localIPs := []map[string]string{
		{"interface": "lo", "ip": "127.0.0.1"},
		{"interface": "ens17", "ip": "64.90.13.19"},
		{"interface": "ens17", "ip": "fe80::1"},
	}
	got := localIPv4ForInterface(localIPs, "ens17")
	if got != "64.90.13.19" {
		t.Fatalf("localIPv4ForInterface = %q, want 64.90.13.19", got)
	}
}

func TestListeningPortRowsFiltersInvalidRows(t *testing.T) {
	ssOutput := `Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp   LISTEN 0      4096          0.0.0.0:22        0.0.0.0:*     users:(("sshd",pid=1,fd=3))
udp   UNCONN 0      0             0.0.0.0:68        0.0.0.0:*
tcp   LISTEN 0      4096          0.0.0.0:*         0.0.0.0:*     users:(("bad",pid=2,fd=3))
tcp   LISTEN 0      4096          [::]:443          [::]:*        users:(("xray",pid=3,fd=3))
`
	rows, skipped := listeningPortRows(ssOutput)
	if len(rows) != 2 {
		t.Fatalf("len(rows) = %d, want 2 rows: %#v", len(rows), rows)
	}
	if skipped != 1 {
		t.Fatalf("skipped = %d, want 1", skipped)
	}
	if rows[0]["port"] != 22 {
		t.Fatalf("first port = %#v, want 22", rows[0]["port"])
	}
	if rows[1]["port"] != 443 {
		t.Fatalf("second port = %#v, want 443", rows[1]["port"])
	}
}
