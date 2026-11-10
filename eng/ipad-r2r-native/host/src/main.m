#import <UIKit/UIKit.h>
void mono_ios_runtime_init(void);
@interface SceneDelegate:UIResponder<UIWindowSceneDelegate>
@property(strong,nonatomic) UIWindow *window;
@end
@implementation SceneDelegate
-(void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
 self.window=[[UIWindow alloc]initWithWindowScene:(UIWindowScene*)scene];
 self.window.rootViewController=[UIViewController new];[self.window makeKeyAndVisible];
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^{mono_ios_runtime_init();});
}
@end
@interface AppDelegate:UIResponder<UIApplicationDelegate>@end
@implementation AppDelegate
-(UISceneConfiguration*)application:(UIApplication*)app configurationForConnectingSceneSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
 UISceneConfiguration*config=[[UISceneConfiguration alloc]initWithName:@"Main" sessionRole:session.role];config.delegateClass=SceneDelegate.class;return config;
}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(AppDelegate.class));}}
