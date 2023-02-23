import mmap
import binascii
import struct
import time

from datetime import datetime

PAD = 0xAA
RECORD_FORMAT = ">QhBBI"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)
BASE_RECORD_FORMAT = RECORD_FORMAT[:-1]
BASE_RECORD_SIZE = struct.calcsize(BASE_RECORD_FORMAT)
WRITE_FORMAT = f">{struct.calcsize(BASE_RECORD_FORMAT)}s{RECORD_FORMAT[-1]}"

assert struct.calcsize(WRITE_FORMAT) == RECORD_SIZE
assert mmap.PAGESIZE % RECORD_SIZE == 0

def calc_file_size(min_capacity):
    min_size = min_capacity * RECORD_SIZE
    if min_size % mmap.PAGESIZE == 0:
        return min_size

    return (int(min_size / mmap.PAGESIZE) + 1) * mmap.PAGESIZE

EMPTY = b'\x00' * RECORD_SIZE
class CircularLog:
    def __init__(self, mapped):
        self.next_free = None
        self.data = mapped
        self.size = int(len(self.data)/RECORD_SIZE)
        self.max_timestamp = 0
        self.clean()

    def __len__(self):
        return self.size

    @classmethod
    def from_file(cls, file_name, min_entries):
        f = open(file_name, "a+b")
        f.truncate(calc_file_size(min_entries)) # "truncate"
        data_log = mmap.mmap(f.fileno(), 0)
        return cls(data_log)

    def clean(self):
        corrupt = 0
        empty = 0
        good = 0
        last_timestamp = None

        for i in range(len(self)):
            offset = i*RECORD_SIZE
            record_data = self.data[offset: offset+RECORD_SIZE]

            if record_data == EMPTY:
                if self.next_free is None:
                    self.next_free = i

                empty += 1
                continue

            timestamp, distance, battery, pad, crc = struct.unpack(RECORD_FORMAT, record_data)
            disk_crc = binascii.crc32(record_data[:-4])
            if disk_crc != crc or pad != PAD:
                if self.next_free is None:
                    self.next_free = i

                record_data = EMPTY
                corrupt += 1
                continue

            if  self.next_free is None and timestamp < self.max_timestamp:
                self.next_free = i

            self.max_timestamp = max(self.max_timestamp, timestamp)
            good += 1

        if self.next_free is None:
            # The oldest record (and therefor the one that gets
            # overwritten next) must be the first one
            self.next_free = 0

        print(good, empty, corrupt)

    def byte_offset(self, record_number=None):
        if record_number is None:
            record_number = self.next_free
        return record_number * RECORD_SIZE

    def page_byte_offset(self):
        return int(self.byte_offset() / mmap.PAGESIZE) * mmap.PAGESIZE

    def write(self, distance, battery):
        timestamp = int(time.time())
        base_record = struct.pack(BASE_RECORD_FORMAT, timestamp, distance, battery, PAD)
        crc = binascii.crc32(base_record)

        struct.pack_into(WRITE_FORMAT, self.data, self.byte_offset(),
                         base_record, crc)

        self.data.flush(self.page_byte_offset(), mmap.PAGESIZE)

        self.next_free += 1
        if self.next_free >= len(self):
            self.next_free = 0

    def read(self, record_number):
        record_offset = self.byte_offset(record_number)
        record_data = self.data[record_offset:record_offset + RECORD_SIZE]

        timestamp, distance, battery, pad, crc = struct.unpack(RECORD_FORMAT, record_data)

        if timestamp == 0:
            return None, None, None

        disk_crc = binascii.crc32(record_data[:-4])

        assert disk_crc == crc
        assert pad == PAD

        return datetime.fromtimestamp(timestamp), distance, battery

    def last_records(self, n=12):
        start = (self.next_free - 1) % len(self)
        ts, distance, battery = self.read(start)
        if ts is None:
            return

        largest_ts = ts
        yield ts, distance, battery
        
        for i in range(1, n):
            entry_number = (start - i) % len(self)
            ts, distance, battery = self.read(entry_number)
            if ts is None or ts > largest_ts:
                break
            yield ts, distance, battery

    def records_from_to(self, start, end):
        # we could do something clever in place, but the dataset will
        # never be that big and this is more reliable
        matches = []
        for timestamp, distance, battery in self.last_records(len(self)):
            if start <= timestamp < end:
                matches.append((timestamp, distance, battery))
            elif timestamp < start:
                break

        matches.reverse()
        return matches
            
