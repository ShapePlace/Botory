package dev.botory.android.data;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

public class PairingUriParserTest {

    @Test
    public void parsesFullBotoryPairUri() {
        String uri = "botory://pair?v=1&hub=hub_9f2a&name=HomePC&lan=192.168.1.42:8765&relay=wss://relay.botory.dev&token=secret123";
        PairingUriParser.PairingConfig cfg = PairingUriParser.parse(uri);

        assertEquals("hub_9f2a", cfg.hubId);
        assertEquals("HomePC", cfg.hubName);
        assertEquals("ws://192.168.1.42:8765", cfg.lanAddress);
        assertEquals("wss://relay.botory.dev", cfg.relayUrl);
        assertEquals("secret123", cfg.token);
    }

    @Test
    public void parsesBareHostAndPort() {
        PairingUriParser.PairingConfig cfg = PairingUriParser.parse("192.168.0.15:8765");
        assertEquals("ws://192.168.0.15:8765", cfg.lanAddress);
        assertNull(cfg.relayUrl);
    }
}
