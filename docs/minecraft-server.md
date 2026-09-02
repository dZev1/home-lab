# Minecraft Server

## Specifications

- Operating System: NixOS
- Server: Fabric Server
- JVM RAM: 6 GB
- Optimization mods: Lithium, ScalableLux, Chunky, Carpet
- Hardware: Deskmini 110, Celeron (+ upcoming i7-7700 upgrade)
- Players: up to 10 concurrent, stable

## World Pre-generation

- Why: avoid real-time chunk-generation lag on limited hardware.
- Radius (pre-loaded):
  - 6000 blocks (overworld)
  - 4000 blocks (the_nether)
  - 4000 block (the_end)

## Connectivity

- Dynamic IP problem (ISP changes IP weekly)
- ddns-updater solution -> domain of my server
- For the DDNS detail and a related reliability incident, check [this link.](networking)

## Backups

### Process

- Disable autosave -> save-all flush -> tar compression -> move to separate disk.
- This order avoids corruption from concurrent writes and makes server stop completely
  for it not to log files even when autosave is disabled.

### Retention

- Weekly rotation, deleting backups older than seven days.

### Incident: Silent Backup Failure

- While performing a restore test for the first time, discovered that all 7 backups
  saved on disk were 0-byte `.tar.gz` files — the backup process had been silently
  failing since it was first set up.
- Root cause: `save-all` doesn't write to disk immediately. With a base
  running ~130k entities at the time (see [130k marker entities
  incident](./minecraft-server.md#incident-130k-marker-entities)), tar compression
  was starting before the world finished writing to disk, resulting in
  corrupt/empty archives.
- Fix: script now uses `save-all flush` to force an immediate write,
  with an increased `sleep` before compression starts, and `nice` to
  reduce I/O priority impact during the process.
- Verified the fix with a successful restore test.
- Lesson learned: always test things before relying on them blindly.

### Incident: 130k marker entities

- One add-on/datapack on the server uses `minecraft:marker` entities to
  place a grave so players can retrieve their items after death.
- Problem: a player died on top of another mob, causing the datapack's
  `minecraft:marker` checks to fail repeatedly and spawn duplicate
  entities — up to 130k of them, lagging the whole server whenever a
  player entered that area.
- Fix: used `carpet-mod` with `max-tick-rate=-1` to gain control over
  server ticking, spawned a bot player to load the affected terrain
  from a distance, and ran `kill @e[type=marker]` to clear all
  duplicated entities.
- Lesson learned: datapacks are user-made and prone to bugs, knowing
  how to debug them matters.

## NixOS Integration

- Automatic backups everyday at 6 AM making use of `systemd.service` + `systemd.timer`.

```nix
systemd.services.minecraft-backup = {
  description = "Daily backup of the minecraft server";
  path = [ pkgs.bash pkgs.gnutar pkgs.tmux ];
  serviceConfig = {
    Type = "oneshot";
    User = "<USER>";
    ExecStart = "/home/<USER>/scripts/minecraft-backup.sh";
  };
};

systemd.timers.minecraft-backup = {
  wantedBy = [ "timers.target" ];
  partOf = [ "minecraft-backup.service" ];
  timerConfig = {
    OnCalendar = "*-*-* 06:00:00";
    Persistent = true;
  };
};
```
