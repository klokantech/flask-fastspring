<?php

$key = '0123456789ABCDEF';
$payload = 'Hello, world!';

$cipher_text = openssl_encrypt($payload, 'AES-128-ECB', $key, OPENSSL_RAW_DATA);
$secure_payload = base64_encode($cipher_text);

$private_key = openssl_pkey_get_private(file_get_contents('test_secure.key'));
openssl_private_encrypt($key, $aes_key_encrypted, $private_key);
$secure_key = base64_encode($aes_key_encrypted);

echo $secure_payload, "\n";
echo $secure_key, "\n";

?>
