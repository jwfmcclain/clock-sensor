set -x
tar cvf - circular_log.py main.py start service.toml | ssh ec2-user@ec2-34-201-116-162.compute-1.amazonaws.com sudo python3 /opt/kou/instance-management/update-instance.py i0-20113a9fe59ce34c5da6b1947fc38bf7
