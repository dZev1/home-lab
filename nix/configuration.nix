{ config, lib, pkgs, ... }:

{
  imports =
    [
      ./hardware-configuration.nix
    ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  networking.hostName = "deskmini-server";

  time.timeZone = "America/Argentina/Buenos_Aires";

  i18n.defaultLocale = "en_US.UTF-8";
  console.keyMap = "es";

  programs.zsh = {
    enable = true;
    autosuggestions.enable = true;
    syntaxHighlighting.enable = true;

    ohMyZsh = {
       enable = true;
       plugins = [ "git" "colored-man-pages" ];
       theme = "gentoo";
    };
  };

  users.users.<USER> = {
     # USER CONFIG HERE
  };

  environment.systemPackages = with pkgs; [
   dmidecode
   fastfetch
   unzip
   tree
   vim
   wget
   curl
   git
   python3
   uv
   tmux
   htop
   jdk25
   neovim
   ripgrep
   stylua
   clang
   tailscale
  ];

  services.openssh = {
     enable = true;
     settings = {
       PermitRootLogin = "no";
       PasswordAuthentication = false;
       KbdInteractiveAuthentication = false;
     };
  };

  services.tailscale.enable = true;

  programs.neovim = {
    enable = true;
    viAlias = true;
    vimAlias = true;
  };

  networking = {
     # Networking config
  };

  virtualisation.docker.enable = true;

  systemd.services.minecraft-backup = {
     description = "Backup diario del server de Minecraft";
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

  # Copy the NixOS configuration file and link it from the resulting system
  # (/run/current-system/configuration.nix). This is useful in case you
  # accidentally delete configuration.nix.
  # system.copySystemConfiguration = true;

  # This option defines the first version of NixOS you have installed on this particular machine,
  # and is used to maintain compatibility with application data (e.g. databases) created on older NixOS versions.
  #
  # Most users should NEVER change this value after the initial install, for any reason,
  # even if you've upgraded your system to a new NixOS release.
  #
  # This value does NOT affect the Nixpkgs version your packages and OS are pulled from,
  # so changing it will NOT upgrade your system - see https://nixos.org/manual/nixos/stable/#sec-upgrading for how
  # to actually do that.
  #
  # This value being lower than the current NixOS release does NOT mean your system is
  # out of date, out of support, or vulnerable.
  #
  # Do NOT change this value unless you have manually inspected all the changes it would make to your configuration,
  # and migrated your data accordingly.
  #
  # For more information, see `man configuration.nix` or https://nixos.org/manual/nixos/stable/options#opt-system.stateVersion .
  system.stateVersion = "26.05"; # Did you read the comment?

}
