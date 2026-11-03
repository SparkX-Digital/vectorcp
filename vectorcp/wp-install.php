<?php
// Executed as the customer, with input on stdin and no password in argv/logs.
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
define('WP_INSTALLING', true);
require $argv[1] . '/wp-load.php';
require ABSPATH . 'wp-admin/includes/upgrade.php';
add_filter('pre_wp_mail', '__return_false');
$result = wp_install($input['title'], $input['admin'], $input['email'], false, '', $input['password']);
if (is_wp_error($result)) { fwrite(STDERR, "WordPress installation failed\n"); exit(1); }
update_option('blog_public', 0);
update_option('permalink_structure', '/%postname%/');
echo json_encode(['installed' => true, 'version' => get_bloginfo('version')]);
