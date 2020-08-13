# Change Top Light color
# https://www.dji.com/jp/robomaster-s1/programming-guide

import time
variable_LedID = 0
list_LedList = RmList()

for i in range(20):
    # 1: rm_define.armor_top_(all,left,right) 
    # 2： rgb
    # 3： rm_define.effect_(always_(on,off),breath,flush,marquee) 
    led_ctrl.set_top_led(rm_define.armor_top_all, i*10, 255-i*10, 0, rm_define.effect_breath)
    time.sleep(1)