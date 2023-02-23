from circular_log import CircularLog
clog = CircularLog.from_file("test-log", 1)

print(len(clog))

write_count = 10000

for i in range(write_count):
    clog.write(i, 0)

read = 0
expect = write_count - 1
for timestamp, distance, battery in clog.last_records(10):
    read += 1
    if expect != distance:
        print(expect, distance)
        assert False
    expect -= 1

print(read)
        
