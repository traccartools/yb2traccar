#!/usr/bin/python3
from functools import reduce

class DataView:
    def __init__(self, array, bytes_per_element=1):
        self.array = array
        self.bytes_per_element = 1
        self.pos = 0

    def __get_binary(self, start_index, byte_count, signed=False):
        integers = [self.array[start_index + x] for x in range(byte_count)]
        bytes = [integer.to_bytes(self.bytes_per_element, byteorder='big', signed=signed) for integer in integers]
        return reduce(lambda a, b: a + b, bytes)

    def getUint(self, bytes):
        start_index = self.pos
        self.pos += bytes
        return int.from_bytes(self.__get_binary(start_index, bytes), byteorder='big')

    def getInt(self, bytes):
        start_index = self.pos
        self.pos += bytes
        return int.from_bytes(self.__get_binary(start_index, bytes), byteorder='big', signed=True)       


    def getUint32(self):
        return self.getUint(4)

    def getUint16(self):
        return self.getUint(2)

    def getUint8(self):
        return self.getUint(1)

    def getInt32(self):
        return self.getInt(4)

    def getInt16(self):
        return self.getInt(2)

    def getInt8(self):
        return self.getInt(1)



def parse(e):
    t = DataView(e)

    i = t.getUint8()
    hasAlt = bool (1 & i)
    hasDtf = bool (2 & i)
    hasLap = bool (4 & i)
    hasPc = bool (8 & i)

    startTime = t.getUint32()
    c = []

    while t.pos < len(e):
    
        boatID = t.getUint16()
        pointsNum = t.getUint16()
        pointsList = [None] * pointsNum

        g = 0
        v = 0
        while v < pointsNum:
            p = t.getUint8()
            t.pos -= 1
            m = {}
            if (bool (128 & p)):
                m["at"] = g["at"] - (32767 & t.getUint16())
                m["lat"] = g["lat"] + t.getInt16()
                m["lon"] = g["lon"] + t.getInt16()

                if (hasAlt):
                    m["alt"] = t.getInt16()

                if (hasDtf):
                    f = t.getInt16()
                    m["dtf"] = g["dtf"] + f
                    if (hasLap):
                        m["lap"] = t.getUint8()

                if (hasPc):
                    m["pc"] = t.getInt16() / 32000
                    m["pc"] += g["pc"] + m["pc"]

            else:
                m["at"] = startTime + t.getUint32()
                m["lat"] = t.getInt32()
                m["lon"] = t.getInt32()

                if (hasAlt):
                    m["alt"] = t.getInt16()

                if (hasDtf):
                    x = t.getInt32()
                    m["dtf"] = x
                    if (hasLap):
                        m["lap"] = t.getUint8()
                
                if (hasPc):
                    m["pc"] = t.getInt32() / 21000000

            pointsList[v] = m
            g = m
            v += 1

        for q in pointsList:
            q["lat"] /= 100000
            q["lon"] /= 100000

        dict = {}
        dict['id'] = boatID
        dict['moments'] = pointsList
        c.append(dict)

    return(c)

