import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { URLForm } from '@/components/transcription/URLForm'
import { UploadForm } from '@/components/transcription/UploadForm'
import { TaskList } from '@/components/transcription/TaskList'
import { Link2, Upload } from 'lucide-react'

export function HomePage() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle>語音轉錄</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="url">
              <TabsList>
                <TabsTrigger value="url">
                  <span className="flex items-center gap-1.5"><Link2 className="h-4 w-4" />從 URL</span>
                </TabsTrigger>
                <TabsTrigger value="upload">
                  <span className="flex items-center gap-1.5"><Upload className="h-4 w-4" />上傳檔案</span>
                </TabsTrigger>
              </TabsList>
              <TabsContent value="url"><URLForm /></TabsContent>
              <TabsContent value="upload"><UploadForm /></TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <div className="lg:col-span-3">
        <Card>
          <CardHeader>
            <CardTitle>任務列表</CardTitle>
          </CardHeader>
          <CardContent>
            <TaskList />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
