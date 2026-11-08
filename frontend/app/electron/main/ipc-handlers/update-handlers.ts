import type { AppConfig } from '@electron/main/app-config';
import type { LogService } from '@electron/main/log-service';

interface UpdateHandlersCallbacks {
  terminateSubprocesses: (update?: boolean) => Promise<void>;
  updateDownloadProgress: (progress: number) => void;
}

/**
 * trodki is local-only and never contacts a release server, so the app updater is disabled:
 * a check always reports "no update" and download/install are no-ops. Update by pulling the
 * repository and rebuilding.
 *
 * The IPC surface is kept so the renderer needs no special casing.
 */
export class UpdateHandlers {
  constructor(
    private readonly logger: LogService,
    private readonly config: AppConfig,
  ) {}

  initialize(_callbacks: UpdateHandlersCallbacks): void {}

  checkForUpdates = async (): Promise<boolean> => {
    this.logger.debug(`Update check skipped (local-only build, dev=${this.config.isDev})`);
    return false;
  };

  downloadUpdate = async (_event: Electron.IpcMainInvokeEvent): Promise<boolean> => false;

  installUpdate = async (): Promise<Error | boolean> => false;
}
