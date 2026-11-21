package dev.botory.android.data;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Pure Java parser for Botory pairing URIs (botory://pair?v=1&hub=...&lan=...&relay=...&token=...).
 * Demonstrates seamless Java + Kotlin interoperability inside the Android app.
 */
public final class PairingUriParser {

    public static final class PairingConfig {
        public final String hubId;
        public final String hubName;
        public final String lanAddress;
        public final String relayUrl;
        public final String token;

        public PairingConfig(String hubId, String hubName, String lanAddress, String relayUrl, String token) {
            this.hubId = hubId;
            this.hubName = hubName;
            this.lanAddress = lanAddress;
            this.relayUrl = relayUrl;
            this.token = token;
        }
    }

    private PairingUriParser() {}

    public static PairingConfig parse(String rawInput) {
        if (rawInput == null) {
            throw new IllegalArgumentException("Input cannot be null");
        }
        String trimmed = rawInput.trim();
        if (trimmed.isEmpty()) {
            throw new IllegalArgumentException("Input cannot be empty");
        }

        if (trimmed.startsWith("ws://") || trimmed.startsWith("wss://")) {
            String hostOnly = trimmed.replaceFirst("^wss?://", "").split("/")[0];
            return new PairingConfig("manual_hub", "Manual Hub (" + hostOnly + ")", trimmed, null, "");
        }

        if (!trimmed.startsWith("botory://pair")) {
            // Treat bare host:port as LAN ws:// URL
            String wsUrl = trimmed.contains(":") ? "ws://" + trimmed : "ws://" + trimmed + ":8765";
            return new PairingConfig("manual_hub", "LAN Hub (" + trimmed + ")", wsUrl, null, "");
        }

        int qIdx = trimmed.indexOf('?');
        if (qIdx < 0 || qIdx == trimmed.length() - 1) {
            throw new IllegalArgumentException("Missing query parameters in botory://pair URI");
        }

        Map<String, String> params = new HashMap<>();
        String query = trimmed.substring(qIdx + 1);
        for (String pair : query.split("&")) {
            int eq = pair.indexOf('=');
            if (eq > 0) {
                String k = decode(pair.substring(0, eq));
                String v = decode(pair.substring(eq + 1));
                params.put(k, v);
            }
        }

        String hubId = params.getOrDefault("hub", "hub_unknown");
        String hubName = params.getOrDefault("name", "Botory HomeHub");
        String lan = params.getOrDefault("lan", "");
        if (!lan.isEmpty() && !lan.startsWith("ws://") && !lan.startsWith("wss://")) {
            lan = "ws://" + lan;
        }
        String relay = params.get("relay");
        String token = params.getOrDefault("token", "");

        return new PairingConfig(hubId, hubName, lan, relay, token);
    }

    private static String decode(String s) {
        try {
            return URLDecoder.decode(s, StandardCharsets.UTF_8.name());
        } catch (UnsupportedEncodingException e) {
            return s;
        }
    }
}
