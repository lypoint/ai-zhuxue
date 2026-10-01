Pod::Spec.new do |s|
  s.name = 'ATAuthSDK_D'
  s.version = '2.14.19'
  s.summary = 'Aliyun Phone Number Verification iOS SDK'
  s.homepage = 'https://help.aliyun.com/zh/pnvs/developer-reference/the-ios-client-access'
  s.license = { :type => 'Proprietary', :text => 'Copyright Alibaba Cloud' }
  s.author = { 'Alibaba Cloud' => 'https://www.aliyun.com' }
  s.platform = :ios, '15.0'
  s.source = { :path => '.' }
  s.vendored_frameworks = 'Vendor/ATAuthSDK_D.xcframework'
end
