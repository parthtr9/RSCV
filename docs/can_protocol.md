# CAN Protocol — Damiao Motors

## Bus Parameters

| Parameter       | Value         |
|-----------------|---------------|
| Nominal bitrate | 1 Mbit/s      |
| Data bitrate    | 5 Mbit/s      |
| Mode            | CAN-FD        |
| Frame format    | Standard (11-bit ID) |

## Feedback Frame (recv_id, e.g. 0x11)

```
Byte  0:    [7:4] status  |  [3:0] motor_id
Bytes 1-2:  pos_u    (16-bit unsigned, big-endian)
Byte  3 + high nibble of Byte 4:  vel_u  (12-bit unsigned)
Low nibble of Byte 4 + Byte 5:    torq_u (12-bit unsigned)
Byte  6:    T_mos   (motor temperature, °C, uint8)
Byte  7:    T_rotor (rotor temperature, °C, uint8)
```

### Decode (linear mapping)

```python
value = x_min + (u / (2**N - 1)) * (x_max - x_min)
```

- Position: N=16, range = ±p_max
- Velocity:  N=12, range = ±v_max
- Torque:    N=12, range = ±t_max

### Motor limits

| Motor    | p_max (rad) | v_max (rad/s) | t_max (Nm) |
|----------|------------|----------------|------------|
| DM8009P  | 12.5       | 45.0           | 54.0       |
| DM4340   | 12.5       | 50.0           | 28.0       |
| DM4340P  | 12.5       | 50.0           | 28.0       |
| DM4310   | 12.5       | 30.0           | 10.0       |

**Verify against `dm_motor_constants.hpp` before implementing** — these values
are extracted from the datasheet and may change in new firmware.

## System Command Frames (send_id, e.g. 0x01)

All system commands use 8-byte payload with `is_fd=True, bitrate_switch=True`.

| Command          | Payload (hex)              |
|------------------|----------------------------|
| Enable motor     | `FF FF FF FF FF FF FF FC`  |
| Disable motor    | `FF FF FF FF FF FF FF FD`  |
| Set zero position| `FF FF FF FF FF FF FF FE`  |
| Clear error      | `FF FF FF FF FF FF FF FB`  |

## MIT-Mode Position Command (send_id)

8-byte frame encoding position, velocity, Kp, Kd, torque feedforward.
See `hardware/damiao.py:encode_mit_command` for the bit-packing layout.

## CAN-ID Map

| Joint    | Send ID | Recv ID |
|----------|---------|---------|
| joint_1  | 0x01    | 0x11    |
| joint_2  | 0x02    | 0x12    |
| joint_3  | 0x03    | 0x13    |
| joint_4  | 0x04    | 0x14    |
| joint_5  | 0x05    | 0x15    |
| joint_6  | 0x06    | 0x16    |
| joint_7  | 0x07    | 0x17    |
| gripper  | 0x08    | 0x18    |

Rule: `recv_id = send_id + 0x10` always.

## Bring-Up Commands

```bash
# Bring up CAN-FD interface
sudo ip link set can0 type can \
  bitrate 1000000 dbitrate 5000000 fd on \
  sample-point 0.75 dsample-point 0.75
sudo ip link set can0 up
sudo ip link set can0 txqueuelen 1000

# Verify
ip -details link show can0
candump can0 -L
```
