# ClaudeMixer: Remote Script fuer Spuren, Clips, Arrangement, Pegel, Fader und Geraete; ersetzt ableton-mcp fuer den Bau.
# JSON {"type": ..., "params": {...}} per TCP 127.0.0.1:9878; ausgefuehrt im Haupt-Thread von Live.
from __future__ import absolute_import
import json
import socket
import threading

try:
    import queue
except ImportError:
    import Queue as queue

from _Framework.ControlSurface import ControlSurface

PORT = 9878
ANTWORT_TIMEOUT_S = 25.0  # load_item und Browser-Pfade brauchen bei grosser Library Sekunden
MAX_ANFRAGE_BYTES = 1 << 20  # groesste echte Anfrage: add_notes eines langen Clips, weit unter 1 MB


def create_instance(c_instance):
    return ClaudeMixer(c_instance)


def _db_aus_text(text):
    t = text.replace('dB', '').strip()
    return float('-inf') if 'inf' in t else float(t)


class ClaudeMixer(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._auftraege = queue.Queue()
        self._spitzen = {}
        self._laeuft = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(('127.0.0.1', PORT))
        self._server.listen(5)
        self._server.settimeout(1.0)
        t = threading.Thread(target=self._annehmen)
        t.daemon = True
        t.start()
        self.log_message('ClaudeMixer bereit auf Port %d' % PORT)

    def disconnect(self):
        self._laeuft = False
        try:
            self._server.close()
        except Exception:
            pass
        ControlSurface.disconnect(self)

    # --- Netz (Nebenthread): nur Auftraege einreihen, nie die Live-API anfassen
    def _annehmen(self):
        while self._laeuft:
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except Exception:
                if not self._laeuft:
                    return
                continue
            t = threading.Thread(target=self._bedienen, args=(client,))
            t.daemon = True
            t.start()

    def _bedienen(self, client):
        try:
            client.settimeout(ANTWORT_TIMEOUT_S)
            puffer = b''
            while True:
                stueck = client.recv(65536)
                if not stueck:
                    return
                puffer += stueck
                # Fremde Programme (Browser, Port-Scanner) sollen keinen Speicher fuellen oder Threads halten
                if not puffer.lstrip().startswith(b'{') or len(puffer) > MAX_ANFRAGE_BYTES:
                    return
                try:
                    anfrage = json.loads(puffer.decode('utf-8'))
                    break
                except ValueError:
                    continue
            fertig = threading.Event()
            ergebnis = {}
            self._auftraege.put((anfrage, ergebnis, fertig))
            if not fertig.wait(ANTWORT_TIMEOUT_S):
                ergebnis.update(status='error', message='Live hat nicht rechtzeitig geantwortet')
            client.sendall(json.dumps(ergebnis).encode('utf-8'))
        except Exception as e:
            self.log_message('ClaudeMixer Client-Fehler: %s' % e)
        finally:
            client.close()

    # --- Haupt-Thread: Live ruft update_display etwa alle 100 ms
    def update_display(self):
        ControlSurface.update_display(self)
        for kanal in self._kanaele():
            if not kanal.has_audio_output:  # MIDI-Spuren haben keine Meter
                continue
            spitze = max(kanal.output_meter_left, kanal.output_meter_right)
            if spitze > self._spitzen.get(kanal.name, 0.0):
                self._spitzen[kanal.name] = spitze
        while not self._auftraege.empty():
            anfrage, ergebnis, fertig = self._auftraege.get()
            try:
                befehl = getattr(self, '_cmd_' + anfrage.get('type', ''), None)
                if befehl is None:
                    raise ValueError('Unbekannter Befehl: %s' % anfrage.get('type'))
                ergebnis.update(status='success', result=befehl(**anfrage.get('params', {})))
            except Exception as e:
                ergebnis.update(status='error', message=str(e))
            fertig.set()

    def _kanaele(self):
        song = self.song()
        return list(song.tracks) + list(song.return_tracks) + [song.master_track]

    def _spur(self, track):
        song = self.song()
        if track == 'master':
            return song.master_track
        if isinstance(track, int):
            return song.tracks[track]
        for t in self._kanaele():
            if t.name == track:
                return t
        raise ValueError('Spur nicht gefunden: %s' % track)

    def _fader_db(self, kanal):
        p = kanal.mixer_device.volume
        return _db_aus_text(p.str_for_value(p.value))

    # --- Befehle
    def _cmd_ping(self):
        return {'ok': True, 'port': PORT}

    def _cmd_meters(self, reset=True):
        # Spitze seit dem letzten Abruf; Meter-Skala von Live (0..1, nicht linear in dB).
        aus = []
        master = self.song().master_track
        for i, k in enumerate(self._kanaele()):
            if not k.has_audio_output:
                continue
            ist_master = k == master  # Master hat kein mute/solo (RuntimeError statt AttributeError)
            aus.append({'index': 'master' if ist_master else i, 'name': k.name,
                        'peak': round(self._spitzen.get(k.name, 0.0), 4), 'fader_db': self._fader_db(k),
                        'mute': False if ist_master else bool(k.mute), 'solo': False if ist_master else bool(k.solo)})
        if reset:
            self._spitzen = {}
        return aus

    def _cmd_set_volume(self, track, db):
        p = self._spur(track).mixer_device.volume
        lo, hi = p.min, p.max
        for _ in range(40):
            mitte = (lo + hi) / 2.0
            if _db_aus_text(p.str_for_value(mitte)) < db:
                lo = mitte
            else:
                hi = mitte
        p.value = hi
        return {'track': track, 'fader_db': _db_aus_text(p.str_for_value(p.value))}

    def _cmd_solo(self, track, on=True):
        self._spur(track).solo = bool(on)
        return {'track': track, 'solo': bool(on)}

    def _cmd_mute(self, track, on=True):
        self._spur(track).mute = bool(on)
        return {'track': track, 'mute': bool(on)}

    # --- Bau-Befehle: Namen und Parameter wie ableton-mcp, damit build.mjs ohne dessen Script (und dessen Datensammlung) laeuft
    def _slot(self, track_index, clip_index):
        return self.song().tracks[int(track_index)].clip_slots[int(clip_index)]

    def _cmd_get_session_info(self):
        s = self.song()
        return {'tempo': s.tempo, 'track_count': len(s.tracks), 'return_track_count': len(s.return_tracks),
                'is_playing': bool(s.is_playing), 'current_song_time': s.current_song_time}

    def _cmd_get_session_snapshot(self):
        return {'cue_points': [{'time': c.time, 'name': c.name} for c in self.song().cue_points],
                'tracks': [t.name for t in self.song().tracks]}

    def _cmd_set_tempo(self, tempo):
        self.song().tempo = float(tempo)
        return {'tempo': self.song().tempo}

    def _cmd_create_midi_track(self, index=-1):
        s = self.song()
        s.create_midi_track(int(index))
        i = len(s.tracks) - 1 if int(index) == -1 else int(index)
        return {'index': i, 'name': s.tracks[i].name}

    def _cmd_set_track_name(self, track_index, name):
        self.song().tracks[int(track_index)].name = name
        return {'name': name}

    def _cmd_create_clip(self, track_index, clip_index, length):
        slot = self._slot(track_index, clip_index)
        if slot.has_clip:
            raise ValueError('Clip-Slot ist belegt')
        slot.create_clip(float(length))
        return {'length': slot.clip.length}

    def _cmd_add_notes_to_clip(self, track_index, clip_index, notes):
        clip = self._slot(track_index, clip_index).clip
        clip.set_notes(tuple((int(n.get('pitch', 60)), float(n.get('start_time', 0)), float(n.get('duration', 0.25)),
                              int(n.get('velocity', 100)), bool(n.get('mute', False))) for n in notes))
        return {'note_count': len(notes)}

    def _cmd_set_clip_name(self, track_index, clip_index, name):
        self._slot(track_index, clip_index).clip.name = name
        return {'name': name}

    def _cmd_delete_clip(self, track_index, clip_index):
        self._slot(track_index, clip_index).delete_clip()
        return {'deleted': True}

    def _cmd_duplicate_session_clip_to_arrangement(self, track_index, clip_index, destination_time):
        t = self.song().tracks[int(track_index)]
        t.duplicate_clip_to_arrangement(t.clip_slots[int(clip_index)].clip, float(destination_time))
        return {'destination_time': destination_time}

    def _cmd_start_playback(self):
        self.song().start_playing()
        return {'playing': True}

    def _cmd_stop_playback(self):
        self.song().stop_playing()
        return {'playing': False}

    def _cmd_set_current_song_time(self, time):
        self.song().current_song_time = float(time)
        return {'time': self.song().current_song_time}

    def _cmd_switch_to_arrangement_view(self):
        self.application().view.show_view('Arranger')
        return {'view': 'Arranger'}

    def _cmd_create_locator(self, name, time):
        # set_or_delete_cue toggelt an der Abspielposition; liegt dort schon ein Marker, nur umbenennen
        s = self.song()
        ziel = float(time)
        da = [c for c in s.cue_points if abs(c.time - ziel) < 1e-3]
        if not da:
            s.current_song_time = ziel
            s.set_or_delete_cue()
            da = [c for c in s.cue_points if abs(c.time - ziel) < 1e-3]
        if not da:
            raise ValueError('Marker bei %s nicht angelegt' % ziel)
        try:
            da[0].name = name
        except Exception:
            pass  # Live 11 erlaubt kein Umbenennen per API
        return {'time': da[0].time, 'name': da[0].name}

    def _cmd_get_browser_items_at_path(self, path):
        teile = [p for p in path.split('/') if p]
        item = getattr(self.application().browser, teile[0])
        for teil in teile[1:]:
            treffer = [c for c in item.children if c.name.lower() == teil.lower()]
            if not treffer:
                return {'path': path, 'items': [], 'error': 'nicht gefunden: %s' % teil}
            item = treffer[0]
        kinder = list(item.children)
        self._browser_cache = dict((c.uri, c) for c in kinder)
        return {'path': path, 'items': [{'name': c.name, 'uri': c.uri, 'is_loadable': c.is_loadable} for c in kinder]}

    def _cmd_load_browser_item(self, track_index, item_uri):
        item = getattr(self, '_browser_cache', {}).get(item_uri)
        if item is None:
            raise ValueError('URI erst per get_browser_items_at_path abrufen: %s' % item_uri)
        self.song().view.selected_track = self.song().tracks[int(track_index)]
        self.application().browser.load_item(item)
        return {'loaded': True, 'item_name': item.name}

    def _cmd_get_device_parameters(self, track_index, device_index=0):
        d = self.song().tracks[int(track_index)].devices[int(device_index)]
        return {'device': {'name': d.name, 'class_name': d.class_name, 'parameters': [
            {'index': i, 'name': p.name, 'value': float(p.value), 'min': float(p.min), 'max': float(p.max)}
            for i, p in enumerate(d.parameters)]}}

    def _cmd_set_device_parameter(self, track_index, device_index, parameter_index, value):
        p = self.song().tracks[int(track_index)].devices[int(device_index)].parameters[int(parameter_index)]
        p.value = max(p.min, min(p.max, float(value)))
        return {'name': p.name, 'value': p.value}

    # --- Geraete (ableton-mcp erreicht die Master-Spur nicht)
    def _effekt(self, name):
        b = self.application().browser
        offen = list(b.audio_effects.children) + list(b.plugins.children)
        while offen:
            item = offen.pop(0)
            if item.name.rsplit('.', 1)[0] == name and item.is_loadable:
                return item
            offen.extend(item.children)
        raise ValueError('Audio-Effekt nicht gefunden: %s' % name)

    def _cmd_effekte(self):
        return [i.name for i in self.application().browser.audio_effects.children]

    def _cmd_load_device(self, track, name):
        spur = self._spur(track)
        self.song().view.selected_track = spur
        self.application().browser.load_item(self._effekt(name))
        return {'track': track, 'devices': [d.name for d in spur.devices]}

    def _cmd_delete_device(self, track, device):
        spur = self._spur(track)
        spur.delete_device(int(device))
        return {'track': track, 'devices': [d.name for d in spur.devices]}

    def _cmd_devices(self, track):
        return [{'index': i, 'name': d.name, 'params': [
            {'name': p.name, 'value': p.value, 'min': p.min, 'max': p.max, 'text': p.str_for_value(p.value)} for p in d.parameters]}
            for i, d in enumerate(self._spur(track).devices)]

    def _cmd_set_param(self, track, device, param, value):
        d = self._spur(track).devices[device]
        p = [x for x in d.parameters if x.name == param]
        if not p:
            raise ValueError('Parameter %s fehlt in %s' % (param, d.name))
        p[0].value = max(p[0].min, min(p[0].max, float(value)))
        return {'device': d.name, 'param': param, 'text': p[0].str_for_value(p[0].value)}
