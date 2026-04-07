# Gas City supervisor cycle
gc-cycle() {
    gc stop && launchctl unload ~/Library/LaunchAgents/com.gascity.supervisor.plist && launchctl load ~/Library/LaunchAgents/com.gascity.supervisor.plist && sleep 2 && gc start && gc status
}
