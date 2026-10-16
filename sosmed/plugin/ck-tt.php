<?php
/**
 * Plugin Name: CK TT (Jembatan TikTok)
 * Description: Menerbitkan video Reels Cekricek.id ke TikTok @cekricekid lewat TikTok Content Posting API (Direct Post, FILE_UPLOAD). Rute REST ck/v1 untuk CK Agen. Pendamping ck-fb.php dan ck-ig.php.
 * Version: 1.2.0
 * Author: Redaksi Cekricek.id
 *
 * Pengaturan: Pengaturan > Jembatan TikTok (options-general.php?page=ck-tt): Client Key, Client Secret (tidak
 * pernah ditampilkan kembali), Hubungkan / Putuskan. Redirect URI yang harus terdaftar di aplikasi TikTok:
 *   https://cekricek.id/wp-admin/options-general.php   (tanpa query string; TikTok menolak parameter)
 *
 * Rute (manage_options, lewat CK Agen wp_baca/wp_tulis):
 *   GET  /ck/v1/tt-info                      akun (open_id, nama), masa token, privasi yang diizinkan, siap/tidak
 *   POST /ck/v1/tt-kirim                     video (URL https MP4 publik), judul (caption, <= 2200 karakter),
 *                                            privasi (SELF_ONLY | PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR),
 *                                            jadwal (ISO, opsional; dijalankan WP-Cron), mode draf|langsung (bawaan draf = Upload to TikTok,
 *                                            masuk kotak masuk aplikasi; sound dipilih dan diterbitkan AFP di aplikasi)
 *   POST /ck/v1/tt-foto   {foto:[URL https di domain terverifikasi], judul, keterangan, mode draf|langsung, privasi, sampul_indeks, jadwal}
 *   GET  /ck/v1/tt-status?id=PUBLISH_ID      status penerbitan (PROCESSING_UPLOAD / PUBLISH_COMPLETE / FAILED)
 *
 * Catatan audit: sebelum aplikasi lolos audit TikTok, hanya privasi SELF_ONLY yang diizinkan (video tidak tampil publik).
 * Token akses berumur 24 jam, token segar 365 hari; disegarkan WP-Cron tiap jam.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

define( 'CK_TT_VERSI', '1.2.0' );
define( 'CK_TT_API', 'https://open.tiktokapis.com/v2/' );
define( 'CK_TT_SCOPE', 'user.info.basic,video.publish,video.upload' );

function ck_tt_redirect() { return admin_url( 'options-general.php?page=ck-tt' ); }
/* TikTok menolak redirect_uri berparameter ("should not contain query parameters"), jadi URI OAuth polos
 * dan didaftarkan persis begini di Login Kit. Callback dikenali lewat state (sama seperti ck-ig). */
function ck_tt_redirect_oauth() { return admin_url( 'options-general.php' ); }
function ck_tt_key() { return trim( (string) get_option( 'ck_tt_client_key', '' ) ); }
function ck_tt_secret() { return trim( (string) get_option( 'ck_tt_client_secret', '' ) ); }
function ck_tt_token() { return trim( (string) get_option( 'ck_tt_token', '' ) ); }

function ck_tt_samar( $data ) {
	$json = wp_json_encode( $data );
	foreach ( array( ck_tt_token(), ck_tt_secret(), (string) get_option( 'ck_tt_refresh', '' ) ) as $r ) {
		if ( strlen( $r ) > 8 ) { $json = str_replace( $r, '***', $json ); }
	}
	return json_decode( $json, true );
}

function ck_tt_log( $baris ) {
	$log = get_option( 'ck_tt_log', array() );
	if ( ! is_array( $log ) ) { $log = array(); }
	array_unshift( $log, array_merge( array( 'waktu' => current_time( 'mysql' ) ), $baris ) );
	update_option( 'ck_tt_log', array_slice( $log, 0, 50 ), false );
}

/* Panggilan API TikTok dengan token akses (JSON). */
function ck_tt_api( $metode, $jalur, $badan = null, $waktu = 45 ) {
	$tok = ck_tt_token();
	if ( '' === $tok ) { return new WP_Error( 'ck_tt_token', 'Belum terhubung ke TikTok. Buka Pengaturan > Jembatan TikTok > Hubungkan.', array( 'status' => 409 ) ); }
	$url  = CK_TT_API . ltrim( $jalur, '/' );
	$args = array( 'timeout' => $waktu, 'headers' => array( 'Authorization' => 'Bearer ' . $tok, 'Content-Type' => 'application/json; charset=UTF-8' ) );
	if ( 'GET' === $metode ) {
		$r = wp_remote_get( $url, $args );
	} else {
		$args['body'] = wp_json_encode( null === $badan ? new stdClass() : $badan );
		$r = wp_remote_post( $url, $args );
	}
	if ( is_wp_error( $r ) ) { return $r; }
	$kode = wp_remote_retrieve_response_code( $r );
	$isi  = json_decode( wp_remote_retrieve_body( $r ), true );
	$err  = isset( $isi['error']['code'] ) ? $isi['error']['code'] : 'ok';
	if ( $kode >= 400 || ( 'ok' !== $err ) ) {
		return new WP_Error( 'ck_tt_api', 'TikTok menolak', array( 'status' => 422, 'http' => $kode, 'tiktok' => ck_tt_samar( $isi ) ) );
	}
	return $isi;
}

/* ---------- OAuth ---------- */
function ck_tt_simpan_token( $j ) {
	update_option( 'ck_tt_token', $j['access_token'], false );
	update_option( 'ck_tt_token_kadaluarsa', time() + (int) ( $j['expires_in'] ?? 86400 ), false );
	if ( ! empty( $j['refresh_token'] ) ) {
		update_option( 'ck_tt_refresh', $j['refresh_token'], false );
		update_option( 'ck_tt_refresh_kadaluarsa', time() + (int) ( $j['refresh_expires_in'] ?? 31536000 ), false );
	}
	if ( ! empty( $j['open_id'] ) ) { update_option( 'ck_tt_open_id', $j['open_id'], false ); }
	if ( ! empty( $j['scope'] ) ) { update_option( 'ck_tt_scope', $j['scope'], false ); }
}

function ck_tt_tukar_kode( $kode ) {
	$r = wp_remote_post( CK_TT_API . 'oauth/token/', array(
		'timeout' => 30,
		'headers' => array( 'Content-Type' => 'application/x-www-form-urlencoded' ),
		'body'    => array(
			'client_key'    => ck_tt_key(),
			'client_secret' => ck_tt_secret(),
			'code'          => $kode,
			'grant_type'    => 'authorization_code',
			'redirect_uri'  => ck_tt_redirect_oauth(),
		),
	) );
	if ( is_wp_error( $r ) ) { return $r; }
	$j = json_decode( wp_remote_retrieve_body( $r ), true );
	if ( empty( $j['access_token'] ) ) { return new WP_Error( 'ck_tt_oauth', 'Tukar kode gagal', array( 'tiktok' => ck_tt_samar( $j ) ) ); }
	ck_tt_simpan_token( $j );
	$me = ck_tt_api( 'GET', 'user/info/?fields=open_id,display_name,avatar_url', null, 20 );
	if ( ! is_wp_error( $me ) && ! empty( $me['data']['user'] ) ) {
		update_option( 'ck_tt_akun', $me['data']['user'], false );
	}
	update_option( 'ck_tt_tersambung_pada', current_time( 'mysql' ), false );
	ck_tt_log( array( 'tahap' => 'tersambung', 'open_id' => $j['open_id'] ?? '', 'scope' => $j['scope'] ?? '' ) );
	return true;
}

function ck_tt_segarkan_token() {
	$rt = (string) get_option( 'ck_tt_refresh', '' );
	if ( '' === $rt ) { return false; }
	$r = wp_remote_post( CK_TT_API . 'oauth/token/', array(
		'timeout' => 30,
		'headers' => array( 'Content-Type' => 'application/x-www-form-urlencoded' ),
		'body'    => array( 'client_key' => ck_tt_key(), 'client_secret' => ck_tt_secret(), 'grant_type' => 'refresh_token', 'refresh_token' => $rt ),
	) );
	if ( is_wp_error( $r ) ) { ck_tt_log( array( 'tahap' => 'segar-gagal', 'galat' => $r->get_error_message() ) ); return false; }
	$j = json_decode( wp_remote_retrieve_body( $r ), true );
	if ( empty( $j['access_token'] ) ) { ck_tt_log( array( 'tahap' => 'segar-gagal', 'tiktok' => ck_tt_samar( $j ) ) ); return false; }
	ck_tt_simpan_token( $j );
	return true;
}
/* Pastikan token segar sebelum dipakai (umur 24 jam). */
function ck_tt_pastikan_token() {
	if ( '' === ck_tt_token() ) { return false; }
	if ( (int) get_option( 'ck_tt_token_kadaluarsa', 0 ) - time() < 20 * MINUTE_IN_SECONDS ) { return ck_tt_segarkan_token(); }
	return true;
}
add_action( 'ck_tt_cek_token', function () { ck_tt_pastikan_token(); } );
add_action( 'init', function () {
	if ( ! wp_next_scheduled( 'ck_tt_cek_token' ) ) { wp_schedule_event( time() + 300, 'hourly', 'ck_tt_cek_token' ); }
} );

/* ---------- Halaman pengaturan ---------- */
add_action( 'admin_menu', function () {
	add_options_page( 'Jembatan TikTok', 'Jembatan TikTok', 'manage_options', 'ck-tt', 'ck_tt_halaman_pengaturan' );
} );

add_action( 'admin_init', function () {
	if ( ! current_user_can( 'manage_options' ) ) { return; }
	$di_halaman = isset( $_GET['page'] ) && 'ck-tt' === $_GET['page'];
	// TikTok mengalihkan ke options-general.php?code=..&state=.. (tanpa page), kenali lewat state.
	$balik_dari_tt = isset( $_GET['code'], $_GET['state'] ) && false !== strpos( (string) ( $_SERVER['REQUEST_URI'] ?? '' ), 'options-general.php' ) && (string) $_GET['state'] === (string) get_transient( 'ck_tt_state' );
	if ( ! $di_halaman && ! $balik_dari_tt ) { return; }
	if ( isset( $_POST['ck_tt_simpan'] ) && check_admin_referer( 'ck_tt_simpan' ) ) {
		update_option( 'ck_tt_client_key', sanitize_text_field( wp_unslash( $_POST['ck_tt_client_key'] ?? '' ) ), false );
		$rahasia = trim( (string) wp_unslash( $_POST['ck_tt_client_secret'] ?? '' ) );
		if ( '' !== $rahasia ) { update_option( 'ck_tt_client_secret', $rahasia, false ); }
		wp_safe_redirect( add_query_arg( 'pesan', 'tersimpan', ck_tt_redirect() ) ); exit;
	}
	if ( isset( $_POST['ck_tt_putus'] ) && check_admin_referer( 'ck_tt_putus' ) ) {
		foreach ( array( 'ck_tt_token', 'ck_tt_refresh', 'ck_tt_open_id', 'ck_tt_akun', 'ck_tt_scope', 'ck_tt_token_kadaluarsa', 'ck_tt_refresh_kadaluarsa', 'ck_tt_tersambung_pada' ) as $o ) { delete_option( $o ); }
		ck_tt_log( array( 'tahap' => 'diputus' ) );
		wp_safe_redirect( add_query_arg( 'pesan', 'diputus', ck_tt_redirect() ) ); exit;
	}
	if ( isset( $_POST['ck_tt_kirim'] ) && check_admin_referer( 'ck_tt_kirim' ) ) {
		$isi = array(
			'video'     => esc_url_raw( (string) wp_unslash( $_POST['ck_tt_video'] ?? '' ) ),
			'judul'     => sanitize_text_field( (string) wp_unslash( $_POST['ck_tt_judul'] ?? '' ) ),
			'privasi'   => in_array( $_POST['ck_tt_privasi'] ?? '', array( 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY' ), true ) ? $_POST['ck_tt_privasi'] : 'SELF_ONLY',
			'sampul_ms' => 1000,
		);
		$h = ck_tt_terbitkan_sekarang( $isi );
		if ( is_wp_error( $h ) ) { set_transient( 'ck_tt_galat', $h->get_error_message() . ' ' . wp_json_encode( $h->get_error_data() ), 5 * MINUTE_IN_SECONDS ); wp_safe_redirect( add_query_arg( 'pesan', 'kirim_gagal', ck_tt_redirect() ) ); exit; }
		wp_safe_redirect( add_query_arg( array( 'pesan' => 'terkirim', 'publish_id' => rawurlencode( $h['publish_id'] ) ), ck_tt_redirect() ) ); exit;
	}
	if ( isset( $_GET['ck_tt_mulai'] ) && check_admin_referer( 'ck_tt_mulai' ) ) {
		$state = wp_generate_password( 24, false );
		set_transient( 'ck_tt_state', $state, 15 * MINUTE_IN_SECONDS );
		$url = 'https://www.tiktok.com/v2/auth/authorize/?' . http_build_query( array(
			'client_key'    => ck_tt_key(),
			'scope'         => CK_TT_SCOPE,
			'response_type' => 'code',
			'redirect_uri'  => ck_tt_redirect_oauth(),
			'state'         => $state,
		) );
		wp_redirect( $url ); exit;
	}
	if ( isset( $_GET['code'] ) ) {
		$state = isset( $_GET['state'] ) ? (string) $_GET['state'] : '';
		if ( ! $state || $state !== get_transient( 'ck_tt_state' ) ) {
			wp_safe_redirect( add_query_arg( 'pesan', 'state', ck_tt_redirect() ) ); exit;
		}
		delete_transient( 'ck_tt_state' );
		$h = ck_tt_tukar_kode( (string) wp_unslash( $_GET['code'] ) );
		if ( is_wp_error( $h ) ) {
			set_transient( 'ck_tt_galat', wp_json_encode( $h->get_error_data() ), 5 * MINUTE_IN_SECONDS );
			wp_safe_redirect( add_query_arg( 'pesan', 'gagal', ck_tt_redirect() ) ); exit;
		}
		wp_safe_redirect( add_query_arg( 'pesan', 'tersambung', ck_tt_redirect() ) ); exit;
	}
	if ( isset( $_GET['error'] ) ) {
		set_transient( 'ck_tt_galat', sanitize_text_field( (string) ( $_GET['error_description'] ?? $_GET['error'] ) ), 5 * MINUTE_IN_SECONDS );
		wp_safe_redirect( add_query_arg( 'pesan', 'gagal', ck_tt_redirect() ) ); exit;
	}
} );

function ck_tt_halaman_pengaturan() {
	$pesan = isset( $_GET['pesan'] ) ? sanitize_key( $_GET['pesan'] ) : '';
	$peta  = array( 'tersimpan' => 'Pengaturan tersimpan.', 'diputus' => 'Sambungan TikTok diputus.', 'tersambung' => 'Tersambung ke TikTok.', 'state' => 'Pengaman state tidak cocok; coba Hubungkan lagi.', 'gagal' => 'Gagal menghubungkan: ' . esc_html( (string) get_transient( 'ck_tt_galat' ) ), 'kirim_gagal' => 'Kirim gagal: ' . esc_html( (string) get_transient( 'ck_tt_galat' ) ), 'terkirim' => 'Video dikirim ke TikTok. publish_id: <code>' . esc_html( (string) ( $_GET['publish_id'] ?? '' ) ) . '</code>' );
	$tok = ck_tt_token(); $akun = (array) get_option( 'ck_tt_akun', array() );
	echo '<div class="wrap"><h1>Jembatan TikTok v' . esc_html( CK_TT_VERSI ) . '</h1>';
	if ( $pesan && isset( $peta[ $pesan ] ) ) { echo '<div class="notice notice-info"><p>' . $peta[ $pesan ] . '</p></div>'; }
	echo '<p>TikTok Content Posting API (Direct Post). Di developers.tiktok.com → aplikasi → Login Kit, daftarkan Redirect URI persis (tanpa query string): <code>' . esc_html( ck_tt_redirect_oauth() ) . '</code>. Scope: <code>' . esc_html( CK_TT_SCOPE ) . '</code>. Sebelum aplikasi lolos audit, video hanya bisa berprivasi "hanya saya".</p>';
	echo '<p><strong>Setelah audit TikTok lolos:</strong> ganti Client Key dengan kunci <em>produksi</em> <code>awtrwya3cjm4i25f</code> (kunci sandbox diawali <code>sb</code>), tempel Client Secret produksi (developers.tiktok.com → Cekricek.id → tab Production → Credentials), Simpan, lalu klik <em>Hubungkan ulang</em>. Tugas harian baru mencerminkan ke TikTok bila kunci produksi tersambung.</p>';
	echo '<h2>1. Aplikasi TikTok</h2><form method="post">'; wp_nonce_field( 'ck_tt_simpan' );
	echo '<table class="form-table"><tr><th>Client Key</th><td><input type="text" name="ck_tt_client_key" value="' . esc_attr( ck_tt_key() ) . '" class="regular-text"></td></tr>';
	echo '<tr><th>Client Secret</th><td><input type="password" name="ck_tt_client_secret" value="" class="regular-text" autocomplete="new-password"><p class="description">Status: ' . ( ck_tt_secret() ? 'tersimpan' : '<strong>kosong</strong>' ) . '. Kosongkan untuk membiarkan yang ada. Tidak pernah ditampilkan kembali.</p></td></tr></table>';
	echo '<p><button class="button button-primary" name="ck_tt_simpan" value="1">Simpan</button></p></form>';
	echo '<h2>2. Sambungan ke akun TikTok</h2>';
	if ( $tok ) {
		echo '<p>Tersambung sebagai <strong>' . esc_html( $akun['display_name'] ?? '?' ) . '</strong>' . ( ! empty( $akun['username'] ) ? ' (@' . esc_html( $akun['username'] ) . ')' : '' ) . ' sejak ' . esc_html( (string) get_option( 'ck_tt_tersambung_pada', '' ) ) . '. Token segar berlaku sampai ' . esc_html( get_date_from_gmt( gmdate( 'Y-m-d H:i:s', (int) get_option( 'ck_tt_refresh_kadaluarsa', 0 ) ), 'Y-m-d' ) ) . ' (akses disegarkan otomatis tiap jam). Scope: ' . esc_html( (string) get_option( 'ck_tt_scope', '' ) ) . '</p>';
		echo '<form method="post" style="display:inline">'; wp_nonce_field( 'ck_tt_putus' ); echo '<button class="button" name="ck_tt_putus" value="1">Putuskan sambungan</button></form> ';
		echo '<a class="button" href="' . esc_url( wp_nonce_url( add_query_arg( 'ck_tt_mulai', '1', ck_tt_redirect() ), 'ck_tt_mulai' ) ) . '">Hubungkan ulang</a>';
	} else {
		if ( ! ck_tt_key() || ! ck_tt_secret() ) { echo '<p><em>Isi Client Key dan Client Secret dulu, lalu Simpan.</em></p>'; }
		echo '<p><a class="button button-primary" href="' . esc_url( wp_nonce_url( add_query_arg( 'ck_tt_mulai', '1', ck_tt_redirect() ), 'ck_tt_mulai' ) ) . '">Hubungkan akun TikTok</a> <span class="description">Masuk sebagai @cekricekid lalu setujui izin.</span></p>';
	}
	if ( $tok ) {
		echo '<h2>3. Kirim video (Direct Post)</h2><form method="post">'; wp_nonce_field( 'ck_tt_kirim' );
		echo '<table class="form-table"><tr><th>URL video MP4</th><td><input type="url" name="ck_tt_video" class="large-text" required placeholder="https://.../video.mp4"></td></tr>';
		echo '<tr><th>Judul / keterangan</th><td><input type="text" name="ck_tt_judul" class="large-text" maxlength="2200"></td></tr>';
		echo '<tr><th>Privasi</th><td><select name="ck_tt_privasi"><option value="SELF_ONLY">Hanya saya</option><option value="MUTUAL_FOLLOW_FRIENDS">Teman</option><option value="PUBLIC_TO_EVERYONE">Publik</option></select></td></tr></table>';
		echo '<p><button class="button button-primary" name="ck_tt_kirim" value="1">Kirim ke TikTok</button></p></form>';
		$pid = isset( $_GET['publish_id'] ) ? (string) wp_unslash( $_GET['publish_id'] ) : '';
		if ( $pid ) {
			$st = ck_tt_api( 'POST', 'post/publish/status/fetch/', array( 'publish_id' => $pid ), 20 );
			echo '<p>Status TikTok untuk <code>' . esc_html( $pid ) . '</code>: <strong>' . esc_html( is_wp_error( $st ) ? $st->get_error_message() : (string) ( $st['data']['status'] ?? '?' ) ) . '</strong> <a class="button" href="' . esc_url( add_query_arg( 'publish_id', rawurlencode( $pid ), ck_tt_redirect() ) ) . '">Segarkan status</a></p>';
		}
	}
	$log = array_slice( (array) get_option( 'ck_tt_log', array() ), 0, 10 );
	if ( $log ) {
		echo '<h2>Sepuluh catatan terakhir</h2><table class="widefat striped"><thead><tr><th>Waktu</th><th>Tahap</th><th>Rincian</th></tr></thead><tbody>';
		foreach ( $log as $b ) { $w = $b['waktu'] ?? ''; $t = $b['tahap'] ?? ''; unset( $b['waktu'], $b['tahap'] ); echo '<tr><td>' . esc_html( $w ) . '</td><td>' . esc_html( $t ) . '</td><td><code>' . esc_html( mb_substr( wp_json_encode( ck_tt_samar( $b ), JSON_UNESCAPED_UNICODE ), 0, 220 ) ) . '</code></td></tr>'; }
		echo '</tbody></table>';
	}
	echo '</div>';
}

/* ---------- Penerbitan: unduh MP4 dari URL publik, init FILE_UPLOAD, PUT berkas ---------- */
function ck_tt_terbitkan_sekarang( $isi ) {
	if ( ! ck_tt_pastikan_token() ) { return new WP_Error( 'ck_tt_tautan', 'Belum terhubung ke TikTok (Pengaturan > Jembatan TikTok).', array( 'status' => 409 ) ); }
	$video = $isi['video'];
	if ( ! function_exists( 'download_url' ) ) { require_once ABSPATH . 'wp-admin/includes/file.php'; }
	$tmp = download_url( $video, 120 );
	if ( is_wp_error( $tmp ) ) { ck_tt_log( array( 'tahap' => 'unduh', 'galat' => $tmp->get_error_message() ) ); return $tmp; }
	$ukuran = filesize( $tmp );
	if ( ! $ukuran || $ukuran > 64 * 1024 * 1024 * 4 ) { @unlink( $tmp ); return new WP_Error( 'ck_tt_ukuran', 'Ukuran video tidak wajar: ' . (int) $ukuran, array( 'status' => 400 ) ); }
	// satu potongan bila <= 64 MB (TikTok: potongan 5–64 MB; berkas < 5 MB tetap satu potongan)
	$chunk = min( $ukuran, 64 * 1024 * 1024 );
	$jumlah = (int) ceil( $ukuran / $chunk );
	$draf = ( $isi['mode'] ?? 'langsung' ) === 'draf';
	$badan_init = array(
		'source_info' => array(
			'source'            => 'FILE_UPLOAD',
			'video_size'        => $ukuran,
			'chunk_size'        => $chunk,
			'total_chunk_count' => $jumlah,
		),
	);
	if ( ! $draf ) { $badan_init['post_info'] = array(
			'title'                    => mb_substr( (string) $isi['judul'], 0, 2200 ),
			'privacy_level'            => $isi['privasi'],
			'disable_duet'             => false,
			'disable_comment'          => false,
			'disable_stitch'           => false,
			'video_cover_timestamp_ms' => (int) ( $isi['sampul_ms'] ?? 1000 ),
		); }
	// draf = "Upload to TikTok": video masuk kotak masuk aplikasi; sound dipilih dan diterbitkan oleh AFP di aplikasi (ketetapan 16 Okt 20.41)
	$init = ck_tt_api( 'POST', $draf ? 'post/publish/inbox/video/init/' : 'post/publish/video/init/', $badan_init, 45 );
	if ( is_wp_error( $init ) ) { @unlink( $tmp ); ck_tt_log( array( 'tahap' => 'init', 'galat' => $init->get_error_data() ) ); return $init; }
	$publish_id = $init['data']['publish_id'] ?? ''; $upload_url = $init['data']['upload_url'] ?? '';
	if ( ! $publish_id || ! $upload_url ) { @unlink( $tmp ); return new WP_Error( 'ck_tt_init', 'Tidak dapat publish_id/upload_url', array( 'status' => 422, 'tiktok' => ck_tt_samar( $init ) ) ); }
	$fh = fopen( $tmp, 'rb' ); $awal = 0; $galat = null;
	for ( $i = 0; $i < $jumlah; $i++ ) {
		$data = fread( $fh, $chunk );
		$akhir = $awal + strlen( $data ) - 1;
		$r = wp_remote_request( $upload_url, array(
			'method'  => 'PUT',
			'timeout' => 180,
			'headers' => array( 'Content-Type' => 'video/mp4', 'Content-Length' => strlen( $data ), 'Content-Range' => "bytes {$awal}-{$akhir}/{$ukuran}" ),
			'body'    => $data,
		) );
		if ( is_wp_error( $r ) ) { $galat = $r->get_error_message(); break; }
		$kode = wp_remote_retrieve_response_code( $r );
		if ( $kode < 200 || $kode >= 300 ) { $galat = 'HTTP ' . $kode . ' ' . mb_substr( wp_remote_retrieve_body( $r ), 0, 200 ); break; }
		$awal = $akhir + 1;
	}
	fclose( $fh ); @unlink( $tmp );
	if ( $galat ) { ck_tt_log( array( 'tahap' => 'unggah', 'publish_id' => $publish_id, 'galat' => $galat ) ); return new WP_Error( 'ck_tt_unggah', 'Unggah ke TikTok gagal: ' . $galat, array( 'status' => 422, 'publish_id' => $publish_id ) ); }
	ck_tt_log( array( 'tahap' => $draf ? 'draf-terkirim' : 'terkirim', 'publish_id' => $publish_id, 'privasi' => $draf ? 'draf' : $isi['privasi'], 'ukuran' => $ukuran ) );
	return array( 'ok' => true, 'status' => $draf ? 'draf-diproses' : 'diproses', 'publish_id' => $publish_id, 'catatan' => 'Cek /ck/v1/tt-status?id=' . $publish_id );
}

/* ---------- Foto/kartu: PULL_FROM_URL (domain harus terverifikasi di aplikasi TikTok), draf ke kotak masuk atau langsung ---------- */
function ck_tt_foto_sekarang( $isi ) {
	if ( ! ck_tt_pastikan_token() ) { return new WP_Error( 'ck_tt_tautan', 'Belum terhubung ke TikTok (Pengaturan > Jembatan TikTok).', array( 'status' => 409 ) ); }
	$draf = ( $isi['mode'] ?? 'draf' ) === 'draf';
	$post_info = array( 'title' => mb_substr( (string) ( $isi['judul'] ?? '' ), 0, 90 ), 'description' => mb_substr( (string) ( $isi['keterangan'] ?? '' ), 0, 4000 ) );
	if ( ! $draf ) { $post_info['privacy_level'] = $isi['privasi'] ?? 'SELF_ONLY'; $post_info['disable_comment'] = false; $post_info['auto_add_music'] = true; }
	$badan = array(
		'post_info'   => $post_info,
		'source_info' => array( 'source' => 'PULL_FROM_URL', 'photo_cover_index' => (int) ( $isi['sampul_indeks'] ?? 0 ), 'photo_images' => array_values( $isi['foto'] ) ),
		'post_mode'   => $draf ? 'MEDIA_UPLOAD' : 'DIRECT_POST',
		'media_type'  => 'PHOTO',
	);
	$r = ck_tt_api( 'POST', 'post/publish/content/init/', $badan, 45 );
	if ( is_wp_error( $r ) ) { ck_tt_log( array( 'tahap' => 'foto-init', 'galat' => $r->get_error_data() ) ); return $r; }
	$publish_id = $r['data']['publish_id'] ?? '';
	ck_tt_log( array( 'tahap' => $draf ? 'foto-draf-terkirim' : 'foto-terkirim', 'publish_id' => $publish_id, 'jumlah' => count( $isi['foto'] ) ) );
	return array( 'ok' => true, 'status' => $draf ? 'draf-diproses' : 'diproses', 'publish_id' => $publish_id, 'catatan' => 'Cek /ck/v1/tt-status?id=' . $publish_id );
}

add_action( 'ck_tt_jadwal_terbit', function ( $isi ) {
	$h = ( $isi['jenis'] ?? 'video' ) === 'foto' ? ck_tt_foto_sekarang( $isi ) : ck_tt_terbitkan_sekarang( $isi );
	if ( is_wp_error( $h ) ) { ck_tt_log( array( 'tahap' => 'cron', 'galat' => $h->get_error_data() ) ); }
}, 10, 1 );

/* ---------- REST ---------- */
add_action( 'rest_api_init', function () {
	$izin = function () { return current_user_can( 'manage_options' ); };

	register_rest_route( 'ck/v1', '/tt-info', array( 'methods' => 'GET', 'permission_callback' => $izin, 'callback' => function () {
		$tok = ck_tt_token();
		$kreator = null;
		if ( $tok ) { ck_tt_pastikan_token(); $kreator = ck_tt_api( 'POST', 'post/publish/creator_info/query/', null, 20 ); }
		return array(
			'versi' => CK_TT_VERSI,
			'token_terisi' => '' !== $tok,
			'token_sampai' => (int) get_option( 'ck_tt_token_kadaluarsa', 0 ) ? gmdate( 'c', (int) get_option( 'ck_tt_token_kadaluarsa' ) ) : null,
			'refresh_sampai' => (int) get_option( 'ck_tt_refresh_kadaluarsa', 0 ) ? gmdate( 'c', (int) get_option( 'ck_tt_refresh_kadaluarsa' ) ) : null,
			'akun' => get_option( 'ck_tt_akun', null ),
			'scope' => get_option( 'ck_tt_scope', null ),
			'kreator' => is_wp_error( $kreator ) || null === $kreator ? null : ( $kreator['data'] ?? null ),
			'galat' => ! $tok ? 'Belum terhubung: Pengaturan > Jembatan TikTok > Hubungkan akun TikTok.' : ( is_wp_error( $kreator ) ? $kreator->get_error_data() : null ),
			'siap' => $tok && ! is_wp_error( $kreator ) && null !== $kreator && ! empty( $kreator['data'] ),
			'sandbox' => 0 === strpos( ck_tt_key(), 'sb' ), // kunci sandbox diawali "sb": posting hanya ke akun privat / hanya saya
			'produksi_siap' => $tok && 0 !== strpos( ck_tt_key(), 'sb' ),
			'log' => array_slice( (array) get_option( 'ck_tt_log', array() ), 0, 10 ),
		);
	} ) );

	register_rest_route( 'ck/v1', '/tt-kirim', array( 'methods' => 'POST', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$v = esc_url_raw( (string) $q->get_param( 'video' ) );
		if ( ! $v || 0 !== strpos( $v, 'https://' ) ) { return new WP_Error( 'ck_tt_video', 'Parameter video wajib URL https publik ke MP4.', array( 'status' => 400 ) ); }
		$privasi = strtoupper( (string) ( $q->get_param( 'privasi' ) ?: 'SELF_ONLY' ) );
		if ( ! in_array( $privasi, array( 'SELF_ONLY', 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR' ), true ) ) { return new WP_Error( 'ck_tt_privasi', 'privasi tidak dikenal.', array( 'status' => 400 ) ); }
		$mode = (string) ( $q->get_param( 'mode' ) ?: 'draf' ); // draf (bawaan, ketetapan AFP 16 Okt 20.41) | langsung
		if ( ! in_array( $mode, array( 'draf', 'langsung' ), true ) ) { return new WP_Error( 'ck_tt_mode', 'mode harus draf atau langsung.', array( 'status' => 400 ) ); }
		$isi = array( 'jenis' => 'video', 'mode' => $mode, 'video' => $v, 'judul' => (string) $q->get_param( 'judul' ), 'privasi' => $privasi, 'sampul_ms' => (int) ( $q->get_param( 'sampul_ms' ) ?: 1000 ) );
		$jadwal = (string) $q->get_param( 'jadwal' );
		if ( '' !== $jadwal ) {
			$t = strtotime( $jadwal ); $sel = $t - time();
			if ( ! $t || $sel < 300 || $sel > 180 * DAY_IN_SECONDS ) { return new WP_Error( 'ck_tt_jadwal', 'Jadwal harus 5 menit sampai 180 hari ke depan (ISO 8601).', array( 'status' => 400 ) ); }
			wp_schedule_single_event( $t, 'ck_tt_jadwal_terbit', array( $isi ) );
			ck_tt_log( array( 'tahap' => 'terjadwal', 'pada' => gmdate( 'c', $t ), 'cuplik' => mb_substr( $isi['judul'], 0, 80 ) ) );
			return array( 'ok' => true, 'status' => 'terjadwal', 'jadwal' => gmdate( 'c', $t ) );
		}
		return ck_tt_terbitkan_sekarang( $isi );
	} ) );

	register_rest_route( 'ck/v1', '/tt-foto', array( 'methods' => 'POST', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$foto = (array) $q->get_param( 'foto' );
		$foto = array_values( array_filter( array_map( 'esc_url_raw', $foto ), function ( $u ) { return 0 === strpos( $u, 'https://' ); } ) );
		if ( ! $foto || count( $foto ) > 35 ) { return new WP_Error( 'ck_tt_foto', 'Parameter foto wajib larik 1–35 URL https (domain terverifikasi di aplikasi TikTok, mis. cekricek.id).', array( 'status' => 400 ) ); }
		$mode = (string) ( $q->get_param( 'mode' ) ?: 'draf' );
		if ( ! in_array( $mode, array( 'draf', 'langsung' ), true ) ) { return new WP_Error( 'ck_tt_mode', 'mode harus draf atau langsung.', array( 'status' => 400 ) ); }
		$privasi = strtoupper( (string) ( $q->get_param( 'privasi' ) ?: 'SELF_ONLY' ) );
		$isi = array( 'jenis' => 'foto', 'mode' => $mode, 'foto' => $foto, 'judul' => (string) $q->get_param( 'judul' ), 'keterangan' => (string) $q->get_param( 'keterangan' ), 'privasi' => $privasi, 'sampul_indeks' => (int) $q->get_param( 'sampul_indeks' ) );
		$jadwal = (string) $q->get_param( 'jadwal' );
		if ( '' !== $jadwal ) {
			$t = strtotime( $jadwal ); $sel = $t - time();
			if ( ! $t || $sel < 300 || $sel > 180 * DAY_IN_SECONDS ) { return new WP_Error( 'ck_tt_jadwal', 'Jadwal harus 5 menit sampai 180 hari ke depan (ISO 8601).', array( 'status' => 400 ) ); }
			wp_schedule_single_event( $t, 'ck_tt_jadwal_terbit', array( $isi ) );
			ck_tt_log( array( 'tahap' => 'foto-terjadwal', 'pada' => gmdate( 'c', $t ), 'cuplik' => mb_substr( $isi['judul'], 0, 80 ) ) );
			return array( 'ok' => true, 'status' => 'terjadwal', 'jadwal' => gmdate( 'c', $t ) );
		}
		return ck_tt_foto_sekarang( $isi );
	} ) );

	register_rest_route( 'ck/v1', '/tt-status', array( 'methods' => 'GET', 'permission_callback' => $izin, 'callback' => function ( WP_REST_Request $q ) {
		$id = sanitize_text_field( (string) $q->get_param( 'id' ) );
		if ( ! $id ) { return new WP_Error( 'ck_tt_id', 'Parameter id (publish_id) wajib.', array( 'status' => 400 ) ); }
		ck_tt_pastikan_token();
		$r = ck_tt_api( 'POST', 'post/publish/status/fetch/', array( 'publish_id' => $id ), 20 );
		return is_wp_error( $r ) ? $r : ck_tt_samar( $r );
	} ) );
} );
