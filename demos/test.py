import os
from ctypes import *
import ctypes
from ctypes.wintypes import *
import time
import numpy as np


def doErrCheck(err_code, descr):
    if err_code < 0:
        print(str(descr) + " errCode: " + str(err_code))
    return err_code


_HERE = os.path.dirname(os.path.abspath(__file__))
hllDll = WinDLL(os.path.join(_HERE, "../DSRemoteConnect64.dll"))

dsconInstance = HANDLE()
doErrCheck(hllDll.dsconCreateInstance(pointer(dsconInstance), 1), "dsconCreateInstance")
charArray = create_string_buffer("10.2.120.255:8999:8001".encode())
doErrCheck(hllDll.dsconConnect(dsconInstance, charArray), "dsconConnect")
numChannels = c_size_t()
doErrCheck(hllDll.dsconGetChannelCount(dsconInstance, byref(numChannels)), "dsconGetChannelCount")
print(numChannels.value)

# Second way of enumerating Channels
labelsPtr = pointer((POINTER(ctypes.c_char_p) * numChannels.value)())
localValue = c_size_t(numChannels.value)
hllDll.dsconEnumerateChannels(dsconInstance, labelsPtr, byref(localValue))
name = (c_char * 50)()
ch_name = ctypes.cast(name, c_char_p)
unit = (c_char * 50)()
ch_unit = ctypes.cast(name, c_char_p)
ch_instances = []

for i in range(0, numChannels.value):
    name = (c_char * len(labelsPtr[0][0][i]))()
    ch_index = ctypes.cast(name, c_char_p)
    ch_index.value = labelsPtr[0][0][i]
    ch_instance = HANDLE()
    hllDll.dsconCreateChannelInstance(dsconInstance, ch_index, pointer(ch_instance))
    ch_instances.append(ch_instance)
    hllDll.dsconChannelGetName(ch_instances[i], ch_name, 50)
    print(ch_name.value)
    hllDll.dsconGetChUnit(ch_instances[i], ch_unit, 50)
    print(ch_unit.value)

doErrCheck(hllDll.dsconChannelSetTransferred(ch_instances[len(ch_instances) - 1], False), 'dsconChannelSetTransferred')
doErrCheck(hllDll.dsconStartMeasurement(dsconInstance), "dsconStartMeasurement")
data2 = ctypes.cast((c_double * 100000)(), POINTER(c_double))
time_stamps2 = ctypes.cast((c_double * 100000)(), POINTER(c_double))
count = 0
while True:
    try:
        countData2 = c_size_t(100000)
        for i in range(len(ch_instances)):
            doErrCheck(hllDll.dsconChannelReadScalarData_2(ch_instances[i], data2, time_stamps2, byref(countData2)),
                       "dsconChannelReadScalarData_2")

        doErrCheck(hllDll.dsconControlChannelWriteData(ch_instances[1], c_double(0.69 + count)),
                       "dsconControlChannelWriteValue1")
        doErrCheck(hllDll.dsconControlChannelWriteData(ch_instances[2], c_double(0.70 + count)),
                   "dsconControlChannelWriteValue2")
        doErrCheck(hllDll.dsconControlChannelWriteData(ch_instances[3], c_double(0.71 + count)),
                   "dsconControlChannelWriteValue3")
        count += 1
    except:
        print("While interrupted")
        break

print("Finally")
doErrCheck(hllDll.dsconStopMeasurement(dsconInstance), "dsconStopMeasurement")
doErrCheck(hllDll.dsconDisconnect(dsconInstance), "")  # this will close Dewesoft.exe and clear the DCOM
for i in range(0, numChannels.value - 1):
    doErrCheck(hllDll.dsconFreeChannelInstance(ch_instances[i]),
               "dsconFreeChannelInstance")  # this will free chnl instances of dll
doErrCheck(hllDll.dsconDestroyInstance(dsconInstance), "dsconDestroyInstance")  # this will free dll instance
