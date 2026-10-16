<?php
/**
 * Plugin Name: CK IG (Jembatan Instagram)
 * Description: Menerbitkan foto dan Reels ke Instagram @cekricekid lewat "Instagram API with Instagram Login" (tanpa tautan Halaman Facebook). Rute REST ck/v1 untuk CK Agen. Terpisah dari ck-fb.php.
 * Version: 2.0.2
 * Author: Redaksi Cekricek.id
 *
 * Pengaturan: Pengaturan > Jembatan Instagram (options-general.php?page=ck-ig):
 *   ID aplikasi Instagram, Rahasia aplikasi Instagram (tidak pernah ditampilkan kembali), tombol Hubungkan / Putuskan.
 *   URL pengalihan yang harus terdaftar di Meta (Instagram > API setup with Instagram login > Business login):
 *   https://cekricek.id/wp-admin/options-general.php   (tanpa query string; Instagram membuangnya)
 *
 * Rute (semua manage_options, lewat CK Agen wp_baca/wp_tulis) — nama sama dengan v1:
 *   GET  /ck/v1/ig-info                 akun (id, username, pengikut), masa berlaku token, siap/tidak
 *   POST /ck/v1/ig-kirim                gambar (URL JPEG publik), keterangan, jadwal (ISO, opsional) -> foto feed
 *   POST /ck/v1/ig-reel                 video (URL MP4 publik), keterangan, bagikan_feed (default true), jadwal -> Reels
 *   GET  /ck/v1/ig-status?id=CONTAINER  status kontainer (FINISHED / IN_PROGRESS / ERROR)
 *   POST /ck/v1/ig-terbitkan            id kontainer -> media_publish
 *   GET  /ck/v1/ig-daftar?jumlah=N      media terakhir akun
 *
 * Izin: instagram_business_basic, instagram_business_content_publish. Token berumur 60 hari dan
 * disegarkan otomatis oleh WP-Cron setiap hari bila sisa umur < 15 hari. Instagram API tidak punya
 * penjadwalan; jadwal dijalankan WP-Cron di sini.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

define( 'CK_IG_VERSI', '2.0.2' );
define( 'CK_IG_GRAPH', 'v26.0' );
define( 'CK_IG_HOST', 'https://graph.instagram.com/' );
define( 'CK_IG_APP_ID_BAWAAN', '1810805310118786' );
define( 'CK_IG_SCOPE', 'instagram_business_basic,instagram_business_content_publish' );

function ck_ig_redirect() { return admin_url( 'options-general.php?page=ck-ig' ); }
/* Instagram membuang query string dari redirect_uri, jadi URI OAuth harus polos (dan didaftarkan persis begini di Meta). */
function ck_ig_redirect_oauth() { return admin_url( 'options-general.php' ); }
function ck_ig_app_id() { $v = trim( (string) get_option( 'ck_ig_app_id', '' ) ); return '' === $v ? CK_IG_APP_ID_BAWAAN : $v; }
function ck_ig_app_secret() { return trim( (string) get_option( 'ck_ig_app_secret', '' ) ); }
function ck_ig_token() { return trim( (string) get_option( 'ck_ig_token', '' ) ); }
function ck_ig_user_id() { return trim( (string) get_option( 'ck_ig_user_id', '' ) ); }

function ck_ig_samar( $data ) {
	$json = wp_json_encode( $data );
	$json = preg_replace( '/access_token=[^&"\\\\]+/', 'access_token=***', $json );
	foreach ( array( ck_ig_token(), ck_ig_app_secret() ) as $rahasia ) {
		if ( $rahasia ) { $json = str_replace( $rahasia, '***', $json ); }
	}
	return json_decode( $json, true );
}

function ck_ig_log( $baris ) {
	$log = get_option( 'ck_ig_log', array() );
	if ( ! is_array( $log ) ) { $log = array(); }
	array_unshift( $log, array_merge( array( 'waktu' => current_time( 'mysql' ) ), $baris ) );
	update_option( 'ck_ig_log', array_slice( $log, 0, 50 ), false );
}

/* Panggilan Graph Instagram (graph.instagram.com) dengan token pengguna Instagram. */
function ck_ig_graph( $metode, $jalur, $param = array(), $waktu = 45 ) {
	$tok = ck_ig_token();
	if ( '' === $tok ) { return new WP_Error( 'ck_ig_token', 'Belum terhubung ke Instagram. Buka Pengaturan > Jembatan Instagram > Hubungkan.', array( 'status' => 409 ) ); }
	$url = CK_IG_HOST . CK_IG_GRAPH . '/' . ltrim( $jalur, '/' );
	$param['access_token'] = $tok;
	$r = ( 'GET' === $metode )
		? wp_remote_get( add_query_arg( $param, $url ), array( 'timeout' => $waktu ) )
		: wp_remote_post( $url, array( 'timeout' => $waktu, 'body' => $param ) );
	if ( is_wp_error( $r ) ) { return $r; }
	$kode = wp_remote_retrieve_response_code( $r );
	$isi  = json_decode( wp_remote_retrieve_body( $r ), true );
	if ( $kode >= 400 || isset( $isi['error'] ) ) {
		return new WP_Error( 'ck_ig_graph', 'Instagram menolak', array( 'status' => 502, 'graph' => ck_ig_samar( $isi ), 'http' => $kode ) );
	}
	return $isi;
}

/* ---------- OAuth: tukar kode -> token pendek -> token panjang ---------- */
function ck_ig_tukar_kode( $kode ) {
	$kode = preg_replace( '/#_$/', '', trim( $kode ) );
	$r = wp_remote_post( 'https://api.instagram.com/oauth/access_token', array(
		'timeout' => 30,
		'body'    => array(
			'client_id'     => ck_ig_app_id(),
			'client_secret' => ck_ig_app_secret(),
			'grant_type'    => 'authorization_code',
			'redirect_uri'  => ck_ig_redirect_oauth(),
			'code'          => $kode,
		),
	) );
	if ( is_wp_error( $r ) ) { return $r; }
	$j = json_decode( wp_remote_retrieve_body( $r ), true );
	if ( empty( $j['access_token'] ) ) {
		return new WP_Error( 'ck_ig_oauth', 'Tukar kode gagal', array( 'graph' => ck_ig_samar( $j ) ) );
	}
	$pendek  = $j['access_token'];
	$user_id = isset( $j['user_id'] ) ? (string) $j['user_id'] : '';
	// token panjang (60 hari)
	$r2 = wp_remote_get( add_query_arg( array(
		'grant_type'    => 'ig_exchange_token',
		'client_secret' => ck_ig_app_secret(),
		'access_token'  => $pendek,
	), CK_IG_HOST . 'access_token' ), array( 'timeout' => 30 ) );
	if ( is_wp_error( $r2 ) ) { return $r2; }
	$j2 = json_decode( wp_remote_retrieve_body( $r2 ), true );
	if ( empty( $j2['access_token'] ) ) {
		return new WP_Error( 'ck_ig_oauth2', 'Tukar ke token panjang gagal', array( 'graph' => ck_ig_samar( $j2 ) ) );
	}
	update_option( 'ck_ig_token', $j2['access_token'], false );
	update_option( 'ck_ig_token_kadaluarsa', time() + (int) ( isset( $j2['expires_in'] ) ? $j2['expires_in'] : 5184000 ), false );
	update_option( 'ck_ig_tersambung_pada', current_time( 'mysql' ), false );
	// user_id dari /me lebih dapat dipercaya
	$me = ck_ig_graph( 'GET', 'me', array( 'fields' => 'user_id,username' ), 20 );
	if ( ! is_wp_error( $me ) && ! empty( $me['user_id'] ) ) { $user_id = (string) $me['user_id']; }
	if ( ! is_wp_error( $me ) && ! empty( $me['username'] ) ) { update_option( 'ck_ig_username', $me['username'], false ); }
	update_option( 'ck_ig_user_id', $user_id, false );
	ck_ig_log( array( 'tahap' => 'tersambung', 'user_id' => $user_id, 'izin' => isset( $j['permissions'] ) ? $j['permissions'] : null ) );
	return true;
}

/* Segarkan token panjang (harus berumur >= 24 jam dan belum kedaluwarsa). */
function ck_ig_segarkan_token() {
	$tok = ck_ig_token();
	if ( '' === $tok ) { return false; }
	$r = wp_remote_get( add_query_arg( array( 'grant_type' => 'ig_refresh_token', 'access_token' => $tok ), CK_IG_HOST . 'refresh_access_token' ), array( 'timeout' => 30 ) );
	if ( is_wp_error( $r ) ) { ck_ig_log( array( 'tahap' => 'segar-gagal', 'galat' => $r->get_error_message() ) ); return false; }
	$j = json_decode( wp_remote_retrieve_body( $r ), true );
	if ( empty( $j['access_token'] ) ) { ck_ig_log( array( 'tahap' => 'segar-gagal', 'graph' => ck_ig_samar( $j ) ) ); return false; }
	update_option( 'ck_ig_token', $j['access_token'], false );
	update_option( 'ck_ig_token_kadaluarsa', time() + (int) ( isset( $j['expires_in'] ) ? $j['expires_in'] : 5184000 ), false );
	ck_ig_log( array( 'tahap' => 'segar', 'sampai' => gmdate( 'c', (int) get_option( 'ck_ig_token_kadaluarsa' ) ) ) );
	return true;
}
add_action( 'ck_ig_cek_token_harian', function () {
	$sisa = (int) get_option( 'ck_ig_token_kadaluarsa', 0 ) - time();
	if ( ck_ig_token() && $sisa < 15 * DAY_IN_SECONDS ) { ck_ig_segarkan_token(); }
} );
add_action( 'init', function () {
	if ( ! wp_next_scheduled( 'ck_ig_cek_token_harian' ) ) { wp_schedule_event( time() + HOUR_IN_SECONDS, 'daily', 'ck_ig_cek_token_harian' ); }
} );

/* ---------- Halaman pengaturan ---------- */
add_action( 'admin_menu', function () {
	add_options_page( 'Jembatan Instagram', 'Jembatan Instagram', 'manage_options', 'ck-ig', 'ck_ig_halaman_pengaturan' );
} );

add_action( 'admin_init', function () {
	if ( ! current_user_can( 'manage_options' ) ) { return; }
	// Instagram mengalihkan ke options-general.php?code=..&state=.. (parameter page dibuang), jadi kenali lewat state.
	$di_halaman_kami = isset( $_GET['page'] ) && 'ck-ig' === $_GET['page'];
	$balik_dari_ig   = isset( $_GET['code'], $_GET['state'] ) && false !== strpos( (string) ( $_SERVER['REQUEST_URI'] ?? '' ), 'options-general.php' ) && (string) $_GET['state'] === (string) get_transient( 'ck_ig_state' );
	if ( ! $di_halaman_kami && ! $balik_dari_ig ) { return; }
	// 1. simpan pengaturan
	if ( isset( $_POST['ck_ig_simpan'] ) && check_admin_referer( 'ck_ig_simpan' ) ) {
		update_option( 'ck_ig_app_id', sanitize_text_field( wp_unslash( $_POST['ck_ig_app_id'] ?? '' ) ), false );
		$rahasia = trim( (string) wp_unslash( $_POST['ck_ig_app_secret'] ?? '' ) );
		if ( '' !== $rahasia ) { update_option( 'ck_ig_app_secret', $rahasia, false ); }
		wp_safe_redirect( add_query_arg( 'pesan', 'tersimpan', ck_ig_redirect() ) ); exit;
	}
	// 2. putuskan
	if ( isset( $_POST['ck_ig_putus'] ) && check_admin_referer( 'ck_ig_putus' ) ) {
		foreach ( array( 'ck_ig_token', 'ck_ig_user_id', 'ck_ig_username', 'ck_ig_token_kadaluarsa', 'ck_ig_tersambung_pada' ) as $o ) { delete_option( $o ); }
		ck_ig_log( array( 'tahap' => 'diputus' ) );
		wp_safe_redirect( add_query_arg( 'pesan', 'diputus', ck_ig_redirect() ) ); exit;
	}
	// 3. mulai login Instagram
	if ( isset( $_GET['ck_ig_mulai'] ) && check_admin_referer( 'ck_ig_mulai' ) ) {
		$state = wp_generate_password( 24, false );
		set_transient( 'ck_ig_state', $state, 15 * MINUTE_IN_SECONDS );
		$url = 'https://www.instagram.com/oauth/authorize?' . http_build_query( array(
			'enable_fb_login'      => '0',
			'force_authentication' => '0',
			'client_id'            => ck_ig_app_id(),
			'redirect_uri'         => ck_ig_redirect_oauth(),
			'response_type'        => 'code',
			'scope'                => CK_IG_SCOPE,
			'state'                => $state,
		) );
		wp_redirect( $url ); exit;
	}
	// 4. kembali dari Instagram
	if ( isset( $_GET['code'] ) ) {
		$state = isset( $_GET['state'] ) ? (string) $_GET['state'] : '';
		if ( ! $state || $state !== get_transient( 'ck_ig_state' ) ) {
			wp_safe_redirect( add_query_arg( 'pesan', 'state', ck_ig_redirect() ) ); exit;
		}
		delete_transient( 'ck_ig_state' );
		$h = ck_ig_tukar_kode( (string) $_GET['code'] );
		if ( is_wp_error( $h ) ) {
			set_transient( 'ck_ig_galat', wp_json_encode( $h->get_error_data() ), 5 * MINUTE_IN_SECONDS );
			wp_safe_redirect( add_query_arg( 'pesan', 'gagal', ck_ig_redirect() ) ); exit;
		}
		wp_safe_redirect( add_query_arg( 'pesan', 'tersambung', ck_ig_redirect() ) ); exit;
	}
	if ( isset( $_GET['error'] ) ) {
		set_transient( 'ck_ig_galat', sanitize_text_field( (string) ( $_GET['error_description'] ?? $_GET['error'] ) ), 5 * MINUTE_IN_SECONDS );
		wp_safe_redirect( add_query_arg( 'pesan', 'gagal', ck_ig_redirect() ) ); exit;
	}
} );

function ck_ig_halaman_pengaturan() {
	$pesan = isset( $_GET['pesan'] ) ? sanitize_key( $_GET['pesan'] ) : '';
	$peta  = array( 'tersimpan' => 'Pengaturan tersimpan.', 'diputus' => 'Sambungan Instagram diputus.', 'tersambung' => 'Tersambung ke Instagram.', 'state' => 'Pengaman state tidak cocok; coba Hubungkan lagi.', 'gagal' => 'Gagal menghubungkan: ' . esc_html( (string) get_transient( 'ck_ig_galat' ) ) );
	$tok   = ck_ig_token();
	$kadal = (int) get_option( 'ck_ig_token_kadaluarsa', 0 );
	echo '<div class="wrap"><h1>Jembatan Instagram v' . esc_html( CK_IG_VERSI ) . '</h1>';
	if ( $pesan && isset( $peta[ $pesan ] ) ) { echo '<div class="notice notice-info"><p>' . $peta[ $pesan ] . '</p></div>'; }
	echo '<p>Memakai <strong>Instagram API with Instagram Login</strong> — tidak memerlukan tautan ke Halaman Facebook. Di Meta for Developers → aplikasi → Kasus penggunaan → Instagram → <em>API setup with Instagram login</em>, daftarkan URL pengalihan persis: <code>' . esc_html( ck_ig_redirect_oauth() ) . '</code></p>';
	echo '<h2>1. Aplikasi Instagram</h2><form method="post">'; wp_nonce_field( 'ck_ig_simpan' );
	echo '<table class="form-table"><tr><th>ID aplikasi Instagram</th><td><input type="text" name="ck_ig_app_id" value="' . esc_attr( ck_ig_app_id() ) . '" class="regular-text"></td></tr>';
	echo '<tr><th>Rahasia aplikasi Instagram</th><td><input type="password" name="ck_ig_app_secret" value="" class="regular-text" autocomplete="new-password"><p class="description">Status: ' . ( ck_ig_app_secret() ? 'tersimpan' : '<strong>kosong</strong>' ) . '. Kosongkan untuk membiarkan yang ada. Tidak pernah ditampilkan kembali.</p></td></tr></table>';
	echo '<p><button class="button button-primary" name="ck_ig_simpan" value="1">Simpan</button></p></form>';
	echo '<h2>2. Sambungan ke akun Instagram</h2>';
	if ( $tok ) {
		echo '<p>Tersambung sebagai <strong>@' . esc_html( (string) get_option( 'ck_ig_username', '?' ) ) . '</strong> (ID ' . esc_html( ck_ig_user_id() ) . ') sejak ' . esc_html( (string) get_option( 'ck_ig_tersambung_pada', '' ) ) . '. Token berlaku sampai ' . esc_html( $kadal ? get_date_from_gmt( gmdate( 'Y-m-d H:i:s', $kadal ), 'Y-m-d H:i' ) : '?' ) . ' (disegarkan otomatis).</p>';
		echo '<form method="post" style="display:inline">'; wp_nonce_field( 'ck_ig_putus' ); echo '<button class="button" name="ck_ig_putus" value="1">Putuskan sambungan</button></form> ';
		echo '<a class="button" href="' . esc_url( wp_nonce_url( add_query_arg( 'ck_ig_mulai', '1', ck_ig_redirect() ), 'ck_ig_mulai' ) ) . '">Hubungkan ulang</a>';
	} else {
		if ( ! ck_ig_app_secret() ) { echo '<p><em>Isi Rahasia aplikasi Instagram dulu, lalu Simpan.</em></p>'; }
		echo '<p><a class="button button-primary" href="' . esc_url( wp_nonce_url( add_query_arg( 'ck_ig_mulai', '1', ck_ig_redirect() ), 'ck_ig_mulai' ) ) . '">Hubungkan akun Instagram</a> <span class="description">Masuk sebagai @cekricekid lalu setujui izin.</span></p>';
	}
	$log = array_slice( (array) get_option( 'ck_ig_log', array() ), 0, 10 );
	if ( $log ) {
		echo '<h2>Sepuluh catatan terakhir</h2><table class="widefat striped"><thead><tr><th>Waktu</th><th>Tahap</th><th>Rincian</th></tr></thead><tbody>';
		foreach ( $log as $b ) { $w = $b['waktu'] ?? ''; $t = $b['tahap'] ?? ''; unset( $b['waktu'], $b['tahap'] ); echo '<tr><td>' . esc_html( $w ) . '</td><td>' . esc_html( $t ) . '</td><td><code>' . esc_html( mb_substr( wp_json_encode( ck_ig_samar( $b ), JSON_UNESCAPED_UNICODE ), 0, 200 ) ) . '</code></td></tr>'; }
		echo '</tbody></table>';
	}
	echo '</div>';
}

/* ---------- Penerbitan ---------- */
function ck_ig_terbitkan_sekarang( $isi ) {
	$ig = ck_ig_user_id();
	if ( '' === $ig || '' === ck_ig_token() ) { return new WP_Error( 'ck_ig_tautan', 'Belum terhubung ke Instagram (Pengaturan > Jembatan Instagram).', array( 'status' => 409 ) ); }
	$k = ck_ig_graph( 'POST', $ig . '/media', $isi, 60 );
	if ( is_wp_error( $k ) ) { ck_ig_log( array( 'tahap' => 'kontainer', 'galat' => $k->get_error_data() ) ); return $k; }
	$cid = isset( $k['id'] ) ? $k['id'] : '';
	if ( ! $cid ) { return new WP_Error( 'ck_ig_kontainer', 'Tidak dapat id kontainer', array( 'status' => 502, 'graph' => ck_ig_samar( $k ) ) ); }
	$video = isset( $isi['media_type'] ) && 'REELS' === $isi['media_type'];
	$status = 'FINISHED'; $s = null;
	// foto pun kadang butuh beberapa detik; tunggu sampai FINISHED (foto maks ±20 detik, video ±50 detik)
	$putaran = $video ? 10 : 4;
	for ( $i = 0; $i < $putaran; $i++ ) {
		$s = ck_ig_graph( 'GET', $cid, array( 'fields' => 'status_code,status' ), 20 );
		$status = is_wp_error( $s ) ? 'IN_PROGRESS' : ( isset( $s['status_code'] ) ? $s['status_code'] : 'IN_PROGRESS' );
		if ( 'FINISHED' === $status || 'ERROR' === $status ) { break; }
		sleep( 5 );
	}
	if ( 'ERROR' === $status ) {
		ck_ig_log( array( 'tahap' => 'proses', 'kontainer' => $cid, 'galat' => ck_ig_samar( $s ) ) );
		return new WP_Error( 'ck_ig_proses', 'Instagram gagal memproses media', array( 'status' => 502, 'kontainer' => $cid, 'graph' => ck_ig_samar( $s ) ) );
	}
	if ( 'FINISHED' !== $status ) {
		ck_ig_log( array( 'tahap' => 'menunggu', 'kontainer' => $cid ) );
		wp_schedule_single_event( time() + 120, 'ck_ig_terbitkan_kontainer', array( $cid, 0 ) );
		return array( 'ok' => true, 'status' => 'menunggu', 'kontainer' => $cid, 'catatan' => 'WP-Cron akan menerbitkan sesudah FINISHED; atau POST /ck/v1/ig-terbitkan dengan id kontainer ini.' );
	}
	$p = ck_ig_graph( 'POST', $ig . '/media_publish', array( 'creation_id' => $cid ), 45 );
	if ( is_wp_error( $p ) ) { ck_ig_log( array( 'tahap' => 'terbit', 'kontainer' => $cid, 'galat' => $p->get_error_data() ) ); return $p; }
	$mid = isset( $p['id'] ) ? $p['id'] : '';
	$m = $mid ? ck_ig_graph( 'GET', $mid, array( 'fields' => 'id,permalink,media_type,timestamp' ), 20 ) : null;
	ck_ig_log( array( 'tahap' => 'terbit', 'media_id' => $mid, 'kontainer' => $cid, 'jenis' => $video ? 'reels' : 'foto' ) );
	return array( 'ok' => true, 'status' => 'terbit', 'media_id' => $mid, 'kontainer' => $cid, 'media' => is_wp_error( $m ) ? null : $m );
}

add_action( 'ck_ig_jadwal_terbit', function ( $isi ) {
	$hasil = ck_ig_terbitkan_sekarang( $isi );
	if ( is_wp_error( $hasil ) ) { ck_ig_log( array( 'tahap' => 'cron', 'galat' => $hasil->get_error_data() ) ); }
}, 10, 1 );

add_action( 'ck_ig_terbitkan_kontainer', function ( $cid, $coba ) {
	$ig = ck_ig_user_id(); if ( '' === $ig ) { return; }
	$s = ck_ig_graph( 'GET', $cid, array( 'fields' => 'status_code' ), 20 );
	$status = is_wp_error( $s ) ? 'IN_PROGRESS' : ( isset( $s['status_code'] ) ? $s['status_code'] : 'IN_PROGRESS' );
	if ( 'FINISHED' === $status ) {
		$p = ck_ig_graph( 'POST', $ig . '/media_publish', array( 'creation_id' => $cid ), 45 );
		ck_ig_log( array( 'tahap' => 'cron-terbit', 'kontainer' => $cid, 'hasil' => is_wp_error( $p ) ? $p->get_error_data() : $p ) );
	} elseif ( 'ERROR' !== $status && $coba < 10 ) {
		wp_schedule_single_event( time() + 120, 'ck_ig_terbitkan_kontainer', array( $cid, $coba + 1 ) );
	} else {
		ck_ig_log( array( 'tahap' => 'cron-gagal', 'kontainer' => $cid, 'status' => $status ) );
	}
}, 10, 2 );

function ck_ig_jadwal_atau_kirim( $isi, $jadwal ) {
	if ( '' !== $jadwal ) {
		$t = strtotime( $jadwal );
		$sel = $t - time();
		if ( ! $t || $sel < 300 || $sel > 180 * DAY_IN_SECONDS ) {
			return new WP_Error( 'ck_ig_jadwal', 'Jadwal harus 5 menit sampai 180 hari ke depan (ISO 8601).', array( 'status' => 400 ) );
		}
		wp_schedule_single_event( $t, 'ck_ig_jadwal_terbit', array( $isi ) );
		ck_ig_log( array( 'tahap' => 'terjadwal', 'pada' => gmdate( 'c', $t ), 'jenis' => isset( $isi['media_type'] ) ? 'reels' : 'foto', 'cuplik' => mb_substr( (string) $isi['caption'], 0, 80 ) ) );
		return array( 'ok' => true, 'status' => 'terjadwal', 'jadwal' => gmdate( 'c', $t ), 'catatan' => 'Diterbitkan WP-Cron; cek /ck/v1/ig-daftar sesudah jamnya.' );
	}
	return ck_ig_terbitkan_sekarang( $isi );
}

/* ---------- REST ---------- */
add_action( 'rest_api_init', function () {
	$izin = function () { return current_user_can( 'manage_options' ); };

	register_rest_route( 'ck/v1', '/ig-info', array( 'methods' => 'GET', 'permission_callback' => $izin, 'callback' => function () {
		$tok = ck_ig_token(); $ig = ck_ig_user_id();
		$akun = ( $tok && $ig ) ? ck_ig_graph( 'GET', 'me', array( 'fields' => 'user_id,username,name,account_type,followers_count,media_count' ), 20 ) : null;
		$batas = ( $tok && $ig ) ? ck_ig_graph( 'GET', $ig . '/content_publishing_limit', array( 'fields' => 'quota_usage,config' ), 20 ) : null;
		$kadal = (int) get_option( 'ck_ig_token_kadaluarsa', 0 );
		return array(
			'versi' => CK_IG_VERSI, 'graph' => CK_IG_GRAPH, 'jalur' => 'instagram-login',
			'token_terisi' => '' !== $tok,
			'token_sampai' => $kadal ? gmdate( 'c', $kadal ) : null,
			'akun' => is_wp_error( $akun ) || null === $akun ? null : $akun,
			'batas_harian' => is_wp_error( $batas ) || null === $batas ? null : $batas,
			'galat' => ! $tok ? 'Belum terhubung: Pengaturan > Jembatan Instagram > Hubungkan akun Instagram.' : ( is_wp_error( $akun ) ? $akun->get_error_data() : null ),
			'siap' => $tok && ! is_wp_error( $akun ) && null !== $akun && ! empty( $akun['username'] ),
			'log' => array_slice( (array) get_option( 'ck_ig_log', array() ), 0, 10 ),
		);
	} ) );

	register_rest_route( 'ck/v1', '/ig-kirim', array( 'methods' => 'POST', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$g = esc_url_raw( (string) $q->get_param( 'gambar' ) );
		if ( ! $g || 0 !== strpos( $g, 'https://' ) ) { return new WP_Error( 'ck_ig_gambar', 'Parameter gambar wajib URL https publik ke JPEG.', array( 'status' => 400 ) ); }
		$isi = array( 'image_url' => $g, 'caption' => (string) $q->get_param( 'keterangan' ) );
		return ck_ig_jadwal_atau_kirim( $isi, (string) $q->get_param( 'jadwal' ) );
	} ) );

	register_rest_route( 'ck/v1', '/ig-reel', array( 'methods' => 'POST', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$v = esc_url_raw( (string) $q->get_param( 'video' ) );
		if ( ! $v || 0 !== strpos( $v, 'https://' ) ) { return new WP_Error( 'ck_ig_video', 'Parameter video wajib URL https publik ke MP4.', array( 'status' => 400 ) ); }
		$isi = array( 'media_type' => 'REELS', 'video_url' => $v, 'caption' => (string) $q->get_param( 'keterangan' ),
			'share_to_feed' => ( null === $q->get_param( 'bagikan_feed' ) ) ? 'true' : ( $q->get_param( 'bagikan_feed' ) ? 'true' : 'false' ) );
		return ck_ig_jadwal_atau_kirim( $isi, (string) $q->get_param( 'jadwal' ) );
	} ) );

	register_rest_route( 'ck/v1', '/ig-status', array( 'methods' => 'GET', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$id = preg_replace( '/[^0-9]/', '', (string) $q->get_param( 'id' ) );
		if ( ! $id ) { return new WP_Error( 'ck_ig_id', 'Parameter id wajib.', array( 'status' => 400 ) ); }
		$r = ck_ig_graph( 'GET', $id, array( 'fields' => 'status_code,status' ), 20 );
		return is_wp_error( $r ) ? $r : ck_ig_samar( $r );
	} ) );

	register_rest_route( 'ck/v1', '/ig-terbitkan', array( 'methods' => 'POST', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$cid = preg_replace( '/[^0-9]/', '', (string) $q->get_param( 'id' ) );
		if ( ! $cid ) { return new WP_Error( 'ck_ig_id', 'Parameter id (kontainer) wajib.', array( 'status' => 400 ) ); }
		$ig = ck_ig_user_id(); if ( '' === $ig ) { return new WP_Error( 'ck_ig_tautan', 'Belum terhubung.', array( 'status' => 409 ) ); }
		$p = ck_ig_graph( 'POST', $ig . '/media_publish', array( 'creation_id' => $cid ), 45 );
		if ( is_wp_error( $p ) ) { return $p; }
		ck_ig_log( array( 'tahap' => 'terbit-manual', 'kontainer' => $cid, 'media_id' => isset( $p['id'] ) ? $p['id'] : '' ) );
		return array( 'ok' => true, 'media_id' => isset( $p['id'] ) ? $p['id'] : '' );
	} ) );

	register_rest_route( 'ck/v1', '/ig-daftar', array( 'methods' => 'GET', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$ig = ck_ig_user_id(); if ( '' === $ig ) { return new WP_Error( 'ck_ig_tautan', 'Belum terhubung.', array( 'status' => 409 ) ); }
		$n = max( 1, min( 25, (int) $q->get_param( 'jumlah' ) ?: 10 ) );
		$r = ck_ig_graph( 'GET', $ig . '/media', array( 'fields' => 'id,media_type,caption,permalink,timestamp,like_count,comments_count', 'limit' => $n ), 20 );
		if ( is_wp_error( $r ) ) { return $r; }
		return array( 'ok' => true, 'media' => isset( $r['data'] ) ? $r['data'] : array(), 'catatan' => array_slice( (array) get_option( 'ck_ig_log', array() ), 0, 10 ) );
	} ) );
} );
