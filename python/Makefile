.DEFAULT_GOAL := all

TARGET_DIR=/Volumes/CIRCUITPY
LIB_DIR=$(TARGET_DIR)/lib

CODE=$(addprefix $(TARGET_DIR)/, code.py)
LIBS=$(addprefix $(LIB_DIR)/, adafruit_vl53l4cd.mpy adafruit_bus_device adafruit_display_text adafruit_bitmap_font adafruit_lc709203f.mpy adafruit_register)

$(TARGET_DIR)/%.py: %.py
	cp $< $@

$(TARGET_DIR)/lib/%: lib/%
	rsync -a $< $(TARGET_DIR)/lib

$(LIB_DIR): 
	mkdir $@

$(LIBS): | $(LIB_DIR)

basic:
	cp basic.py $(TARGET_DIR)/code.py

clean:
	rm -f $(CODE)
	rm -rf $(LIB_DIR)

all: $(CODE) $(LIBS)



