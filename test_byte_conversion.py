#!/usr/bin/env python3
"""
Test different byte conversion methods to match mobile app exactly
"""

import hashlib

def big_int_to_full_bytes_v1(big_int):
    """Original implementation"""
    if big_int == 0:
        return bytes([0])
    
    byte_list = []
    temp = big_int
    
    while temp > 0:
        byte_list.insert(0, temp & 0xff)
        temp = temp >> 8
    
    return bytes(byte_list)

def big_int_to_full_bytes_v2(big_int):
    """Alternative: Python's to_bytes with calculated length"""
    if big_int == 0:
        return bytes([0])
    
    # Calculate minimum bytes needed
    bit_length = big_int.bit_length()
    byte_length = (bit_length + 7) // 8
    
    return big_int.to_bytes(byte_length, byteorder='big')

def big_int_to_full_bytes_v3(big_int):
    """Alternative: Fixed 256-byte length (2048 bits)"""
    return big_int.to_bytes(256, byteorder='big')

def test_conversions():
    """Test different conversion methods"""
    
    # Shared secret from Newsletter 169
    shared_secret = 3762477069636953956559424100898320143859022925256195687386863078032361213008173244107944089943861176552806558425157514172569702072656212561349421261158103160273454504594177832185503414414971059251643814484175013393715545539661384786630028762451668816276540801546905413807694713643885293003863423320100614142340260595739978424638664522636049724119099413911233436862543951251175395364748637752258192104549537639221205360987260316478232551110065836309596830702310726996511206773538895083194928687959931073052527669247996814657638444833775842280370249845984079412173120928606400366783709916329545429272059107987278601649
    
    print("=== TESTING BYTE CONVERSION METHODS ===")
    print(f"Shared Secret: {shared_secret}")
    print()
    
    methods = [
        ("V1 - Original", big_int_to_full_bytes_v1),
        ("V2 - Calculated Length", big_int_to_full_bytes_v2),
        ("V3 - Fixed 256 bytes", big_int_to_full_bytes_v3)
    ]
    
    for name, method in methods:
        try:
            bytes_result = method(shared_secret)
            aes_key = hashlib.sha256(bytes_result).digest()[:16]
            
            print(f"{name}:")
            print(f"  Bytes Length: {len(bytes_result)}")
            print(f"  Bytes (hex): {bytes_result.hex()}")
            print(f"  AES Key: {aes_key.hex()}")
            print()
            
        except Exception as e:
            print(f"{name}: ERROR - {e}")
            print()

if __name__ == "__main__":
    test_conversions()