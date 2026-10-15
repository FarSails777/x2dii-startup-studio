#import <Cocoa/Cocoa.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

@interface InstallerApp : NSObject <NSApplicationDelegate>
@property NSWindow *window;
@property NSPopUpButton *presetsPopup;
@property NSPopUpButton *logoPopup;
@property NSButton *animationSwitch;
@property NSImageView *preview;
@property NSTextField *imageLabel;
@property NSTextField *videoLabel;
@property NSTextField *statusLabel;
@property NSTextView *logView;
@property NSURL *imageURL;
@property NSURL *videoURL;
@property NSTask *running;
@property NSMutableArray<NSButton *> *buttons;
@property NSMutableArray<NSDictionary *> *presets;
@end

@implementation InstallerApp

- (NSTextField *)text:(NSString *)value size:(CGFloat)size color:(NSColor *)color {
    NSTextField *view = [NSTextField wrappingLabelWithString:value];
    view.font = [NSFont systemFontOfSize:size];
    view.textColor = color;
    return view;
}

- (NSButton *)button:(NSString *)title action:(SEL)action {
    NSButton *view = [NSButton buttonWithTitle:title target:self action:action];
    view.bezelStyle = NSBezelStyleRounded;
    [self.buttons addObject:view];
    return view;
}

- (NSStackView *)stack:(NSUserInterfaceLayoutOrientation)orientation spacing:(CGFloat)spacing {
    NSStackView *view = [NSStackView stackViewWithViews:@[]];
    view.orientation = orientation;
    view.alignment = orientation == NSUserInterfaceLayoutOrientationVertical
        ? NSLayoutAttributeLeading : NSLayoutAttributeCenterY;
    view.spacing = spacing;
    return view;
}

- (NSView *)card:(NSStackView *)contents {
    NSView *view = [NSView new];
    view.wantsLayer = YES;
    view.layer.backgroundColor = [NSColor colorWithCalibratedRed:.115 green:.135 blue:.165 alpha:1].CGColor;
    view.layer.borderColor = [NSColor colorWithWhite:1 alpha:.085].CGColor;
    view.layer.borderWidth = 1;
    view.layer.cornerRadius = 16;
    contents.translatesAutoresizingMaskIntoConstraints = NO;
    [view addSubview:contents];
    [NSLayoutConstraint activateConstraints:@[
        [contents.leadingAnchor constraintEqualToAnchor:view.leadingAnchor constant:20],
        [contents.trailingAnchor constraintEqualToAnchor:view.trailingAnchor constant:-20],
        [contents.topAnchor constraintEqualToAnchor:view.topAnchor constant:18],
        [contents.bottomAnchor constraintEqualToAnchor:view.bottomAnchor constant:-18]
    ]];
    return view;
}

- (NSURL *)presetsFolder {
    NSURL *support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                           inDomains:NSUserDomainMask].firstObject;
    NSURL *folder = [support URLByAppendingPathComponent:@"X2DII Startup Studio/Presets" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES
                                           attributes:nil error:nil];
    return folder;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.buttons = [NSMutableArray array];
    NSArray *saved = [NSUserDefaults.standardUserDefaults arrayForKey:@"StartupPresets"];
    self.presets = saved ? saved.mutableCopy : [NSMutableArray array];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 960, 750)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                  NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"X2D II 开机工作室";
    self.window.minSize = NSMakeSize(840, 700);
    self.window.appearance = [NSAppearance appearanceNamed:NSAppearanceNameDarkAqua];
    self.window.backgroundColor = [NSColor colorWithCalibratedRed:.065 green:.08 blue:.105 alpha:1];
    [self.window center];

    NSStackView *root = [self stack:NSUserInterfaceLayoutOrientationVertical spacing:16];
    root.translatesAutoresizingMaskIntoConstraints = NO;
    [self.window.contentView addSubview:root];
    [NSLayoutConstraint activateConstraints:@[
        [root.leadingAnchor constraintEqualToAnchor:self.window.contentView.leadingAnchor constant:26],
        [root.trailingAnchor constraintEqualToAnchor:self.window.contentView.trailingAnchor constant:-26],
        [root.topAnchor constraintEqualToAnchor:self.window.contentView.topAnchor constant:22],
        [root.bottomAnchor constraintEqualToAnchor:self.window.contentView.bottomAnchor constant:-20]
    ]];

    NSImageView *icon = [NSImageView new];
    icon.image = [[NSImage alloc] initWithContentsOfFile:
        [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"assets/AppIcon.png"]];
    icon.imageScaling = NSImageScaleProportionallyUpOrDown;
    [icon.widthAnchor constraintEqualToConstant:64].active = YES;
    [icon.heightAnchor constraintEqualToConstant:64].active = YES;
    NSTextField *title = [self text:@"X2D II 开机工作室" size:26 color:NSColor.labelColor];
    title.font = [NSFont systemFontOfSize:26 weight:NSFontWeightBold];
    NSStackView *heading = [self stack:NSUserInterfaceLayoutOrientationVertical spacing:4];
    [heading addArrangedSubview:title];
    [heading addArrangedSubview:[self text:@"开机画面、动画与方案预设" size:13
                                       color:NSColor.secondaryLabelColor]];
    NSStackView *header = [self stack:NSUserInterfaceLayoutOrientationHorizontal spacing:15];
    [header addArrangedSubview:icon];
    [header addArrangedSubview:heading];
    [root addArrangedSubview:header];

    NSStackView *presetContents = [self stack:NSUserInterfaceLayoutOrientationVertical spacing:9];
    NSTextField *presetHeading = [self text:@"方案预设" size:14 color:NSColor.labelColor];
    presetHeading.font = [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold];
    [presetContents addArrangedSubview:presetHeading];
    NSStackView *presetRow = [self stack:NSUserInterfaceLayoutOrientationHorizontal spacing:9];
    self.presetsPopup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    self.presetsPopup.target = self;
    self.presetsPopup.action = @selector(loadPreset:);
    [self.presetsPopup.widthAnchor constraintGreaterThanOrEqualToConstant:300].active = YES;
    [presetRow addArrangedSubview:self.presetsPopup];
    [presetRow addArrangedSubview:[self button:@"保存当前方案…" action:@selector(savePreset:)]];
    [presetRow addArrangedSubview:[self button:@"删除预设" action:@selector(deletePreset:)]];
    [presetContents addArrangedSubview:presetRow];
    NSView *presetCard = [self card:presetContents];
    [root addArrangedSubview:presetCard];
    [presetCard.widthAnchor constraintEqualToAnchor:root.widthAnchor].active = YES;
    [self refreshPresets];

    NSStackView *logoContents = [self stack:NSUserInterfaceLayoutOrientationVertical spacing:10];
    NSTextField *logoTitle = [self text:@"01  静态开机图" size:16 color:NSColor.labelColor];
    logoTitle.font = [NSFont systemFontOfSize:16 weight:NSFontWeightSemibold];
    [logoContents addArrangedSubview:logoTitle];
    NSView *previewBox = [NSView new];
    previewBox.wantsLayer = YES;
    previewBox.layer.backgroundColor = NSColor.blackColor.CGColor;
    previewBox.layer.cornerRadius = 10;
    previewBox.layer.masksToBounds = YES;
    [previewBox.heightAnchor constraintEqualToConstant:185].active = YES;
    self.preview = [NSImageView new];
    self.preview.imageScaling = NSImageScaleProportionallyUpOrDown;
    [self.preview setContentCompressionResistancePriority:NSLayoutPriorityDefaultLow
                                           forOrientation:NSLayoutConstraintOrientationHorizontal];
    self.preview.translatesAutoresizingMaskIntoConstraints = NO;
    [previewBox addSubview:self.preview];
    [NSLayoutConstraint activateConstraints:@[
        [self.preview.leadingAnchor constraintEqualToAnchor:previewBox.leadingAnchor],
        [self.preview.trailingAnchor constraintEqualToAnchor:previewBox.trailingAnchor],
        [self.preview.topAnchor constraintEqualToAnchor:previewBox.topAnchor],
        [self.preview.bottomAnchor constraintEqualToAnchor:previewBox.bottomAnchor]
    ]];
    [logoContents addArrangedSubview:previewBox];
    [previewBox.widthAnchor constraintEqualToAnchor:logoContents.widthAnchor].active = YES;
    self.logoPopup = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.logoPopup addItemsWithTitles:@[@"原厂白 H", @"飞思 PHASE ONE", @"自定义图片"]];
    self.logoPopup.target = self;
    self.logoPopup.action = @selector(changeLogo:);
    [logoContents addArrangedSubview:self.logoPopup];
    [logoContents addArrangedSubview:[self button:@"添加图片…" action:@selector(chooseImage:)]];
    self.imageLabel = [self text:@"黑底居中 · PNG / JPEG" size:11
                             color:NSColor.secondaryLabelColor];
    [logoContents addArrangedSubview:self.imageLabel];
    NSView *logoCard = [self card:logoContents];

    NSStackView *animationContents = [self stack:NSUserInterfaceLayoutOrientationVertical spacing:13];
    NSTextField *animationTitle = [self text:@"02  开机动画" size:16 color:NSColor.labelColor];
    animationTitle.font = [NSFont systemFontOfSize:16 weight:NSFontWeightSemibold];
    [animationContents addArrangedSubview:animationTitle];
    self.animationSwitch = [NSButton checkboxWithTitle:@"开机时播放动画" target:self action:NULL];
    self.animationSwitch.state = NSControlStateValueOn;
    [animationContents addArrangedSubview:self.animationSwitch];
    [animationContents addArrangedSubview:[self text:@"静态开机图之后播放。关闭后直接进入拍照界面。"
                                            size:12 color:NSColor.secondaryLabelColor]];
    [animationContents addArrangedSubview:[self button:@"选择视频…" action:@selector(chooseVideo:)]];
    self.videoLabel = [self text:@"未选择视频：沿用相机当前动画。" size:12
                             color:NSColor.secondaryLabelColor];
    [animationContents addArrangedSubview:self.videoLabel];
    [animationContents addArrangedSubview:[self text:@"MP4 / MOV / M4V · 0.2–2.4 秒\n首次开启动画必须选择视频。"
                                            size:11 color:NSColor.tertiaryLabelColor]];
    NSView *animationCard = [self card:animationContents];

    NSStackView *columns = [self stack:NSUserInterfaceLayoutOrientationHorizontal spacing:16];
    columns.distribution = NSStackViewDistributionFillEqually;
    [columns addArrangedSubview:logoCard];
    [columns addArrangedSubview:animationCard];
    [logoCard.widthAnchor constraintEqualToAnchor:animationCard.widthAnchor].active = YES;
    [logoCard.heightAnchor constraintEqualToConstant:350].active = YES;
    [animationCard.heightAnchor constraintEqualToAnchor:logoCard.heightAnchor].active = YES;
    [root addArrangedSubview:columns];
    [columns.widthAnchor constraintEqualToAnchor:root.widthAnchor].active = YES;

    NSStackView *actions = [self stack:NSUserInterfaceLayoutOrientationHorizontal spacing:12];
    NSButton *apply = [self button:@"应用到相机" action:@selector(applySelection:)];
    apply.bezelColor = [NSColor colorWithCalibratedRed:.18 green:.59 blue:.92 alpha:1];
    [actions addArrangedSubview:apply];
    [actions addArrangedSubview:[self button:@"检查相机" action:@selector(checkCamera:)]];
    self.statusLabel = [self text:@"USB 连接方式请选择“大容量存储”" size:12
                              color:NSColor.secondaryLabelColor];
    [actions addArrangedSubview:self.statusLabel];
    [root addArrangedSubview:actions];

    NSScrollView *scroll = [NSScrollView new];
    scroll.hasVerticalScroller = YES;
    scroll.borderType = NSNoBorder;
    scroll.wantsLayer = YES;
    scroll.layer.cornerRadius = 10;
    scroll.layer.backgroundColor = [NSColor colorWithCalibratedRed:.035 green:.045 blue:.06 alpha:1].CGColor;
    self.logView = [NSTextView new];
    self.logView.editable = NO;
    self.logView.selectable = YES;
    self.logView.backgroundColor = NSColor.clearColor;
    self.logView.textColor = [NSColor colorWithWhite:.86 alpha:1];
    self.logView.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightRegular];
    self.logView.string = @"准备就绪。连接相机后可先检查相机。\n";
    scroll.documentView = self.logView;
    [root addArrangedSubview:scroll];
    [scroll.widthAnchor constraintEqualToAnchor:root.widthAnchor].active = YES;
    [scroll.heightAnchor constraintGreaterThanOrEqualToConstant:110].active = YES;
    [self.logoPopup selectItemAtIndex:1];
    [self updatePreview];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)append:(NSString *)text {
    self.logView.string = [self.logView.string stringByAppendingString:text];
    [self.logView scrollToEndOfDocument:nil];
}

- (void)refreshPresets {
    [self.presetsPopup removeAllItems];
    [self.presetsPopup addItemWithTitle:@"当前编辑方案"];
    for (NSDictionary *preset in self.presets)
        [self.presetsPopup addItemWithTitle:preset[@"name"] ?: @"未命名方案"];
    [self.presetsPopup selectItemAtIndex:0];
}

- (void)updatePreview {
    NSInteger selected = self.logoPopup.indexOfSelectedItem;
    NSString *path = selected == 1
        ? [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"assets/phaseone-preview.png"]
        : selected == 2 ? self.imageURL.path : nil;
    self.preview.image = path ? [[NSImage alloc] initWithContentsOfFile:path] : nil;
    if (selected == 0) {
        NSImage *factory = [[NSImage alloc] initWithSize:NSMakeSize(1024, 768)];
        [factory lockFocus];
        [NSColor.blackColor setFill];
        NSRectFill(NSMakeRect(0, 0, 1024, 768));
        [@"H" drawAtPoint:NSMakePoint(430, 265) withAttributes:@{
            NSFontAttributeName:[NSFont boldSystemFontOfSize:205],
            NSForegroundColorAttributeName:NSColor.whiteColor
        }];
        [factory unlockFocus];
        self.preview.image = factory;
    }
}

- (void)changeLogo:(id)sender {
    if (self.logoPopup.indexOfSelectedItem == 2 && !self.imageURL) [self chooseImage:sender];
    else [self updatePreview];
}

- (void)chooseImage:(id)sender {
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.allowedContentTypes = @[UTTypePNG, UTTypeJPEG];
    if ([panel runModal] == NSModalResponseOK) {
        self.imageURL = panel.URL;
        self.imageLabel.stringValue = panel.URL.lastPathComponent;
        [self.logoPopup selectItemAtIndex:2];
    } else if (!self.imageURL && self.logoPopup.indexOfSelectedItem == 2) {
        [self.logoPopup selectItemAtIndex:1];
    }
    [self updatePreview];
}

- (void)chooseVideo:(id)sender {
    NSOpenPanel *panel = NSOpenPanel.openPanel;
    panel.allowedContentTypes = @[[UTType typeWithFilenameExtension:@"mp4"],
                                  [UTType typeWithFilenameExtension:@"mov"],
                                  [UTType typeWithFilenameExtension:@"m4v"]];
    if ([panel runModal] == NSModalResponseOK) {
        self.videoURL = panel.URL;
        self.videoLabel.stringValue = panel.URL.lastPathComponent;
    }
}

- (void)loadPreset:(id)sender {
    NSInteger index = self.presetsPopup.indexOfSelectedItem - 1;
    if (index < 0 || index >= self.presets.count) return;
    NSDictionary *preset = self.presets[index];
    NSString *logo = preset[@"logo"];
    [self.logoPopup selectItemAtIndex:[logo isEqualToString:@"original"] ? 0 :
                                      [logo isEqualToString:@"phase"] ? 1 : 2];
    self.imageURL = [preset[@"image"] length] ? [NSURL fileURLWithPath:preset[@"image"]] : nil;
    self.videoURL = [preset[@"video"] length] ? [NSURL fileURLWithPath:preset[@"video"]] : nil;
    self.animationSwitch.state = [preset[@"animation"] boolValue] ? NSControlStateValueOn : NSControlStateValueOff;
    self.imageLabel.stringValue = self.imageURL ? self.imageURL.lastPathComponent : @"黑底居中 · PNG / JPEG";
    self.videoLabel.stringValue = self.videoURL ? self.videoURL.lastPathComponent : @"未选择视频：沿用相机当前动画。";
    [self updatePreview];
}

- (NSURL *)copyPresetFile:(NSURL *)source kind:(NSString *)kind error:(NSError **)error {
    if (!source) return nil;
    NSString *name = [NSString stringWithFormat:@"%@-%@.%@", NSUUID.UUID.UUIDString,
                      kind, source.pathExtension.lowercaseString];
    NSURL *target = [[self presetsFolder] URLByAppendingPathComponent:name];
    return [NSFileManager.defaultManager copyItemAtURL:source toURL:target error:error] ? target : nil;
}

- (void)savePreset:(id)sender {
    if (self.logoPopup.indexOfSelectedItem == 2 && !self.imageURL) {
        [self append:@"请先添加自定义图片。\n"]; return;
    }
    if (self.animationSwitch.state == NSControlStateValueOn && !self.videoURL) {
        [self append:@"保存整套方案前，请选择视频。\n"]; return;
    }
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"保存开机方案";
    alert.informativeText = @"会保存开机图、动画开关和选中的视频。";
    [alert addButtonWithTitle:@"保存"];
    [alert addButtonWithTitle:@"取消"];
    NSTextField *name = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 260, 26)];
    name.placeholderString = @"例如：飞思经典";
    alert.accessoryView = name;
    if ([alert runModal] != NSAlertFirstButtonReturn) return;
    NSString *title = [name.stringValue stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!title.length) { [self append:@"预设名称不能为空。\n"]; return; }
    NSError *error = nil;
    NSURL *image = [self copyPresetFile:self.logoPopup.indexOfSelectedItem == 2 ? self.imageURL : nil
                                  kind:@"image" error:&error];
    if (error) { [self append:[NSString stringWithFormat:@"保存图片失败：%@\n", error.localizedDescription]]; return; }
    NSURL *video = [self copyPresetFile:self.animationSwitch.state == NSControlStateValueOn ? self.videoURL : nil
                                  kind:@"video" error:&error];
    if (error) { [self append:[NSString stringWithFormat:@"保存视频失败：%@\n", error.localizedDescription]]; return; }
    NSString *logo = self.logoPopup.indexOfSelectedItem == 0 ? @"original" :
                     self.logoPopup.indexOfSelectedItem == 1 ? @"phase" : @"custom";
    [self.presets addObject:@{@"name":title, @"logo":logo,
                              @"image":image.path ?: @"", @"video":video.path ?: @"",
                              @"animation":@(self.animationSwitch.state == NSControlStateValueOn)}];
    [NSUserDefaults.standardUserDefaults setObject:self.presets forKey:@"StartupPresets"];
    [self refreshPresets];
    [self.presetsPopup selectItemAtIndex:self.presets.count];
    [self loadPreset:nil];
    [self append:[NSString stringWithFormat:@"已保存预设：%@。\n", title]];
}

- (void)deletePreset:(id)sender {
    NSInteger index = self.presetsPopup.indexOfSelectedItem - 1;
    if (index < 0 || index >= self.presets.count) return;
    NSDictionary *preset = self.presets[index];
    for (NSString *key in @[@"image", @"video"])
        if ([preset[key] length]) [NSFileManager.defaultManager removeItemAtPath:preset[key] error:nil];
    [self.presets removeObjectAtIndex:index];
    [NSUserDefaults.standardUserDefaults setObject:self.presets forKey:@"StartupPresets"];
    [self refreshPresets];
    self.imageURL = nil;
    self.videoURL = nil;
    [self.logoPopup selectItemAtIndex:1];
    self.animationSwitch.state = NSControlStateValueOn;
    self.imageLabel.stringValue = @"黑底居中 · PNG / JPEG";
    self.videoLabel.stringValue = @"未选择视频：沿用相机当前动画。";
    [self updatePreview];
    [self append:@"已删除预设。\n"];
}

- (void)checkCamera:(id)sender { [self run:@[@"check"]]; }

- (void)applySelection:(id)sender {
    NSString *logo = self.logoPopup.indexOfSelectedItem == 0 ? @"original" :
                     self.logoPopup.indexOfSelectedItem == 1 ? @"phase" : @"custom";
    if ([logo isEqualToString:@"custom"] && !self.imageURL) {
        [self append:@"请先添加自定义图片。\n"]; return;
    }
    BOOL animated = self.animationSwitch.state == NSControlStateValueOn;
    NSMutableArray<NSString *> *args = [@[@"apply", @"--logo", logo, @"--animation",
                                          animated ? @"on" : @"off"] mutableCopy];
    if ([logo isEqualToString:@"custom"]) [args addObjectsFromArray:@[@"--image", self.imageURL.path]];
    if (animated && self.videoURL) [args addObjectsFromArray:@[@"--video", self.videoURL.path]];
    [self run:args];
}

- (void)run:(NSArray<NSString *> *)arguments {
    if (self.running) return;
    NSTask *task = [NSTask new];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/python3"];
    NSString *script = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"studio.py"];
    task.arguments = [@[[script copy]] arrayByAddingObjectsFromArray:arguments];
    NSMutableDictionary *environment = NSProcessInfo.processInfo.environment.mutableCopy;
    environment[@"PATH"] = @"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin";
    environment[@"PYTHONUNBUFFERED"] = @"1";
    task.environment = environment;
    NSPipe *pipe = NSPipe.pipe;
    task.standardOutput = pipe;
    task.standardError = pipe;
    __weak typeof(self) weakSelf = self;
    pipe.fileHandleForReading.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        if (!data.length) return;
        NSString *line = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf append:line ?: @""]; });
    };
    task.terminationHandler = ^(NSTask *finished) {
        dispatch_async(dispatch_get_main_queue(), ^{
            pipe.fileHandleForReading.readabilityHandler = nil;
            [weakSelf append:finished.terminationStatus == 0 ? @"完成。\n\n" : @"操作未完成。\n\n"];
            BOOL applying = [arguments.firstObject isEqualToString:@"apply"];
            weakSelf.statusLabel.stringValue = finished.terminationStatus == 0
                ? (applying ? @"已应用 · 下次开机生效" : @"相机检查完成") : @"请查看操作记录";
            weakSelf.running = nil;
            for (NSButton *button in weakSelf.buttons) button.enabled = YES;
        });
    };
    [self append:[NSString stringWithFormat:@"\n▶ %@\n", [arguments.firstObject isEqualToString:@"apply"]
                  ? @"应用开机方案" : @"检查相机"]];
    self.statusLabel.stringValue = @"正在与相机通信…";
    for (NSButton *button in self.buttons) button.enabled = NO;
    NSError *error = nil;
    if ([task launchAndReturnError:&error]) self.running = task;
    else {
        [self append:[NSString stringWithFormat:@"启动失败：%@\n", error.localizedDescription]];
        self.statusLabel.stringValue = @"启动失败";
        for (NSButton *button in self.buttons) button.enabled = YES;
    }
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        InstallerApp *delegate = [InstallerApp new];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
