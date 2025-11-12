#!/usr/bin/env python3

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)
G = 2

def calculate_server_public_key(server_private_key):
    """
    Calculate server public key from private key using DH: G^private_key mod P
    """
    server_private_key_int = int(server_private_key)
    server_public_key = pow(G, server_private_key_int, P)
    return server_public_key

if __name__ == "__main__":
    # Server private key for newsletter ID 169
    server_private_key = "1855699527122823605301096117990787629509201203106440200973732878362536081808"
    
    print("=== NEWSLETTER ID 169 - SERVER PUBLIC KEY ===")
    print(f"Server Private Key: {server_private_key}")
    
    # Calculate public key
    server_public_key = calculate_server_public_key(server_private_key)
    
    print(f"Server Public Key: {server_public_key}")
    print(f"Server Public Key (hex): {hex(server_public_key)[2:]}")
    
    print("\n=== FOR MOBILE APP AMAZON-Q ===")
    print("Use this server public key to encrypt test credentials:")
    print(f'"{hex(server_public_key)[2:]}"')
    
    print("\n=== VERIFICATION INFO ===")
    print(f"Newsletter ID: 169")
    print(f"DH Parameters: RFC 3526 Group 14 (P={P.bit_length()} bits, G={G})")
    print(f"Public Key Length: {server_public_key.bit_length()} bits")