<?php
$root = $argv[1];
$domain = $argv[2];
$path = $root . '/wp-config.php';
$config = file_get_contents($path);
foreach (['WP_SITEURL', 'WP_HOME'] as $key) {
    $config = str_replace("define('$key', 'http://$domain');", "define('$key', 'https://$domain');", $config);
}
if (file_put_contents($path, $config, LOCK_EX) === false) exit(1);
require $root . '/wp-load.php';
update_option('siteurl', 'https://' . $domain);
update_option('home', 'https://' . $domain);
echo "HTTPS URLs updated\n";
