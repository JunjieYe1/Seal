

import serial
import time

def read_serial_data():
    ser = None
    buffer = ""  # 用于累积从串行端口读取的数据

    try:
        # 请根据实际情况替换串行端口和波特率
        ser = serial.Serial('COM5', 9600, timeout=None)  # 设置超时为None以持续等待数据

        while True:
            data = ser.read(ser.in_waiting or 1).decode('iso-8859-1')  # 读取所有可用的数据
            buffer += data  # 将新数据追加到缓冲区

            # 查找缓冲区中是否有两个'$'符号
            start_pos = buffer.find('$')
            if start_pos != -1:  # 找到第一个'$'
                end_pos = buffer.find('$', start_pos + 1)  # 找到第二个'$'
                if end_pos != -1:  # 如果找到两个'$'
                    segment = buffer[start_pos + 1:end_pos]  # 提取两个'$'之间的内容
                    print(segment)  # 打印内容
                    buffer = buffer[end_pos:]  # 从缓冲区删除已处理的部分
            time.sleep(0.1)  # 稍微延迟，避免过度占用CPU

    except serial.SerialException as e:
        print(f"串口异常: {e}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        if ser:
            ser.close()  # 确保在退出程序时关闭串行端口

read_serial_data()
